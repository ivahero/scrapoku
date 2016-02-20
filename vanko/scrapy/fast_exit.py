import os
import six
import signal
import logging
import time
import threading

from scrapy.utils.misc import load_object
from scrapy.crawler import CrawlerProcess
from scrapy.utils.ossignal import install_shutdown_handlers
from twisted.internet import reactor

from . import CustomSettings
from ..utils.signal import catch_break


CustomSettings.register(
    FASTEXIT_GRACE_SECS=4,
    FASTEXIT_FORCE_SECS=3,
    FASTEXIT_ALL_CRAWLERS=True,
    )


class FastExit(object):
    logger = logging.getLogger(__name__.rpartition('.')[2])

    installed = False
    cprocess = None
    singleton = None

    @classmethod
    def get_instance(cls, crawler, exit_handler=None):
        if not cls.singleton:
            cls.singleton = cls(crawler)
        if exit_handler:
            cls.singleton.exit_handler = exit_handler
        return cls.singleton

    def __init__(self, crawler, exit_handler=None):
        self.crawler = crawler
        settings = crawler.settings
        self.name = type(self).__name__

        self.grace_secs = settings.getint('FASTEXIT_GRACE_SECS')
        self.force_secs = settings.getint('FASTEXIT_FORCE_SECS')
        self.all_crawlers = settings.getbool('FASTEXIT_ALL_CRAWLERS')

        user_handler = settings.get('FASTEXIT_USER_HANDLER', None)
        if isinstance(user_handler, basestring):
            user_handler = load_object(user_handler)
        assert callable(user_handler) or user_handler is None, \
            '{}: FASTEXIT_USER_HANDLER must be callable'.format(self.name)
        self.user_handler = user_handler
        self.exit_handler = exit_handler

        self.saved_requests = set()
        self.atexit_called = False
        self.alarm_canceler = None
        self.last_sig_time = None
        self.last_sig_num = None

        if not FastExit.installed:
            self.install()
            FastExit.installed = True

        FastExit.singleton = self

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def install(self):
        handler = signal.getsignal(signal.SIGINT)
        try:
            cprocess = six.get_method_self(handler)
        except AttributeError:
            cprocess = None
        assert isinstance(cprocess, CrawlerProcess), \
            '{}: Must be running under CrawlerProcess!'.format(self.name)

        FastExit.cprocess = cprocess
        install_shutdown_handlers(self.signal_shutdown)
        catch_break(self.signal_shutdown, winonly=True, signals=False)
        self.logger.debug('%s: Handlers installed', self.name)

    def signal_shutdown(self, signum=None, stacktrace=None):
        self.logger.info('%s: Starting graceful shutdown (signal:%s)',
                         self.name, signum)
        if signum is not None:
            self.last_sig_time = time.time()
            self.last_sig_num = signum
        self.print_spiders('grace')

        try:
            install_shutdown_handlers(self.force_shutdown)
        except ValueError:
            # ValueError('signal.signal works only from main thread')
            # occurs because on windows we are called from background
            # thread vanko.utils.multiprocessing.Process2._break_waiter()
            reactor.callLater(0,
                              install_shutdown_handlers, self.force_shutdown)
        reactor.addSystemEventTrigger('before', 'shutdown', self.at_exit)
        reactor.callFromThread(self.cprocess._graceful_stop_reactor)

        self.call_later(self.grace_secs, self.force_shutdown)

    def force_shutdown(self, signum=None, stacktrace=None):
        if signum is not None and self.last_sig_num == signum and \
                time.time() - self.last_sig_time < 0.9:
            self.logger.info('%s: Ignoring spurious signal (signal:%s)',
                             self.name, signum)
            return
        self.logger.info('%s: Forcing unclean shutdown (signal:%s)',
                         self.name, signum)
        self.print_spiders('force')
        try:
            install_shutdown_handlers(signal.SIG_IGN)
        except ValueError:
            # ValueError('signal.signal works only from main thread')
            # occurs because due to win32 signals limitation we use
            # background alarm thread on Windows.
            reactor.callLater(0, install_shutdown_handlers, signal.SIG_IGN)
        reactor.callFromThread(self.cprocess._stop_reactor)
        self.call_later(self.force_secs, self.kill_process)

    def kill_process(self, signum=None, stacktrace=None):
        self.call_later(0, None)
        self.print_spiders('exit')
        self.at_exit()
        os._exit(2)

    def at_exit(self):
        if self.atexit_called:
            self.logger.debug('Prevent another at_exit()')
            return
        self.atexit_called = True

        self.save_unfinished_requests()

        spiders = [crawler.spider for crawler in self.get_crawlers()]
        if not spiders:
            spiders = None
        elif len(spiders) == 1:
            spiders = spiders[0]

        if self.user_handler:
            self.user_handler(spiders)
            self.user_handler = None
        if self.exit_handler:
            self.exit_handler(spiders)
            self.exit_handler = None

        self.logger.info('Process finished')

    def get_crawlers(self):
        return self.cprocess.crawlers if self.all_crawlers else [self.crawler]

    def save_unfinished_requests(self):
        count = 0
        for crawler in self.get_crawlers():
            slot = crawler.engine.slot
            if slot:
                for request in slot.inprogress:
                    spider = crawler.spider
                    if (spider, request) not in self.saved_requests:
                        self.logger.debug('Saving spider %s request %s',
                                          spider.name, request.url)
                        self.saved_requests.add((spider, request))
                        slot.scheduler.enqueue_request(
                            request.replace(dont_filter=True))
                        count += 1
        self.logger.info('Saved %d unfinished requests', count)

    def print_spiders(self, stage):
        for crawler in self.get_crawlers():
            spider = crawler.spider
            slot = crawler.engine.slot
            urls = []
            if slot:
                urls = [request.url for request in slot.inprogress]
            self.logger.debug('Active requests of spider %s in "%s" stage: %s',
                              spider.name, stage, ' '.join(urls))

    def call_later(self, delay, func):
        if self.alarm_canceler:
            self.alarm_canceler.set()
            self.alarm_canceler = None
        if not func:
            return
        if delay > 0:
            self.alarm_canceler = canc = threading.Event()
            t = threading.Thread(target=self.alarmer, args=(delay, func, canc))
            t.setDaemon(False)
            t.start()
        else:
            func()

    def alarmer(self, delay, func, canceler):
        curtime = time.time()
        endtime = curtime + delay
        while endtime - curtime > 0:
            time.sleep(endtime - curtime)
            curtime = time.time()
        if not canceler.is_set():
            func()
