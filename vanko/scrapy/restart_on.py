import os
import logging
import time
import re
import requests
import traceback

from scrapy import signals
from scrapy.exceptions import NotConfigured
from collections import defaultdict
from threading import current_thread
from twisted.internet import reactor, threads
from requests.exceptions import ConnectionError

from ..utils.heroku import HerokuRestart
from . import ShowIP, FastExit, CustomSettings


CustomSettings.register(
    RESTARTON_ENABLED=True,
    RESTARTON_SILENCE_REQUESTS=True,
    RESTARTON_PAGECOUNT=0,
    RESTARTON_ITEMCOUNT=0,
    RESTARTON_TIMEOUT=0,
    RESTARTON_ERRORCOUNT=10,
    RESTARTON_PRO_TIMEOUT=10.0,
    RESTARTON_DEL_ACTION='reset,purge,all=crawl',
    RESTARTON_METHOD='auto',  # stop, exit, restart, pro, auto
    RESTARTON_COMMAND='',
    )


class RestartOn(object):
    """
    This extension will restart the heroku dyno or refresh upstream proxy
    or just stop current linux process when a condition is triggered.
    """

    refresh_selector = 'http://localhost/_PRO_/REFRESH/'
    requests_logger = 'requests.packages.urllib3'
    progress_report_sec = 5.0
    progress_poll_sec = 0.5
    robust_handler = True
    logger = logging.getLogger(__name__.rpartition('.')[2])

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        if not crawler.settings.getbool('RESTARTON_ENABLED'):
            self.logger.info('%s is disabled', type(self).__name__)
            raise NotConfigured

        self.crawler = crawler
        self.restart_on = {}
        self.counter = defaultdict(int)
        self.timeout_task = None
        self.restart_in_progress = False

        s = crawler.settings
        self.method = s.get('RESTARTON_METHOD')
        assert self.method in 'auto finish fast stop exit restart pro'.split()

        if self.method == 'auto':
            if s.getbool('HEROKU'):
                self.method = 'restart'
            elif os.environ.get('http_proxy', '').startswith('http://'):
                self.method = 'pro'
            elif s.get('WEBDRIVER_BROWSER') and s.get('PROXY'):
                self.method = 'pro'
            else:
                self.method = 'fast'
            self.logger.debug('Restart method: %s', self.method)

        self.pro_timeout = s.getfloat('RESTARTON_PRO_TIMEOUT')
        self.del_action = s.get('RESTARTON_DEL_ACTION')
        self.command = s.get('RESTARTON_COMMAND')

        self._condition('errorcount', 'error_count', 'spider_error')
        self._condition('pagecount', 'page_count', 'response_received')
        self._condition('timeout', 'spider_opened', None)
        self._condition('itemcount', 'item_scraped', None)
        self._condition(None, 'spider_closed', None)

        if s.getbool('RESTARTON_SILENCE_REQUESTS'):
            logging.getLogger(self.requests_logger).setLevel(logging.WARNING)

    def _condition(self, name, method, signal):
        if name is not None:
            self.restart_on[name] = self.crawler.settings.getfloat(
                'RESTARTON_' + name.upper())
        if name is None or self.restart_on[name]:
            self.crawler.signals.connect(
                getattr(self, method),
                signal=getattr(signals, (signal or method)))

    def _event(self, name, spider, restart=True):
        self.counter[name] += 1
        flag = self.counter[name] == self.restart_on[name]
        if flag and restart:
            self.restart(spider, name)
            self.counter[name] = 0

    def error_count(self, failure, response, spider):
        self._event('errorcount', spider)

    def page_count(self, response, request, spider):
        self._event('pagecount', spider)

    def item_scraped(self, item, spider):
        self._event('itemcount', spider)

    def spider_opened(self, spider):
        self.timeout_task = reactor.callLater(self.restart_on['timeout'],
                                              self.restart, spider, 'timeout')

    def spider_closed(self, spider):
        if self.timeout_task and self.timeout_task.active():
            self.timeout_task.cancel()

    def restart(self, spider, reason):
        self._spider = spider
        self._reason = reason
        m = self.method
        self.logger.info('Refreshing spider (%s) with reason "%s"', m, reason)
        if m == 'restart':
            self.fast_exit(restart=True)
        elif m == 'fast':
            self.fast_exit()
        elif m == 'stop':
            self.crawler.stop()
        elif m == 'exit':
            self.pause_engine()
            self.stop_engine()
            self.logger.info('Application terminated on condition.')
            os._exit(0)
        elif m == 'finish':
            self.crawler.engine.close_spider(spider, reason='finished')
        elif m == 'pro':
            threads.deferToThread(self._refresh_pro_singleton)

    def _at_exit(self, spiders):
        controller = HerokuRestart()
        command = controller.shell_quote(self.command or
                                         controller.get_command())
        if self.del_action:
            mo = re.search(r'(--action|ACTION)=([\w,]+)', command)
            if mo:
                argname = mo.group(1)
                actions = mo.group(2).split(',')
                for del_action in self.del_action.split(','):
                    del_action, _, replacement = del_action.partition('=')
                    if del_action in actions:
                        if replacement:
                            actions[actions.index[del_action]] = replacement
                        else:
                            actions.remove(del_action)
                new_action = '{}={}'.format(argname, ','.join(actions))
                command = re.sub(r'%s=[\w,]+' % argname, new_action, command)
        controller.restart(stop_delay=0, command=command)

    def fast_exit(self, restart=False):
        fast_exit = FastExit.get_instance(self.crawler, self._at_exit,
                                          self.robust_handler)
        fast_exit.signal_shutdown()

    def stop_engine(self):
        self.crawler.engine.close_spider(self._spider,
                                         'restarton_%s' % self._reason)

    def pause_engine(self):
        engine = self.crawler.engine
        downloader = engine.downloader

        engine.pause()
        self.logger.debug('Engine paused')

        t1 = t2 = t = time.time()
        while downloader.active and t < t1 + self.pro_timeout:
            time.sleep(self.progress_poll_sec)
            if t > t2 + self.progress_report_sec:
                t2 = t
                self.logger.debug('Still %d active downloads pending',
                                  len(downloader.active))
            t = time.time()

        if not downloader.active:
            return True

        self.logger.warning('Still %d downloads pending after %.1fs',
                            len(downloader.active), self.pro_timeout)

    def resume_engine(self):
        self.crawler.engine.unpause()
        self.logger.debug('Engine resumed')

    def _refresh_pro_singleton(self):
        if not self.restart_in_progress:
            try:
                self.restart_in_progress = True
                self._refresh_pro()
            finally:
                self.restart_in_progress = False
        else:
            self.logger.warning('Refresh already running')

    def _refresh_pro(self):
        # "pro" method
        proxies = ShowIP.get_proxies()

        try:
            self.pause_engine()

            try:
                self.logger.debug('Refreshing from %s', current_thread().name)
                res = requests.get(self.refresh_selector, proxies=proxies)
                if res.status_code != 200:
                    self.logger.warning('The refresh request status is %d',
                                        res.status_code)
            except ConnectionError:
                self.logger.warning(traceback.format_exc(limit=6))

            time.sleep(self.progress_report_sec)

            t1 = time.time()
            via = None
            while time.time() < t1 + self.pro_timeout:
                try:
                    via = ShowIP.get_ip(proxies)
                    break
                except ConnectionError:
                    time.sleep(self.progress_poll_sec)
            self.logger.info('Now via: %s', via)

        finally:
            self.resume_engine()
