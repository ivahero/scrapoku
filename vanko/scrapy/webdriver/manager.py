"""
This source code is based on the scrapy_webdriver project located at
  https://github.com/brandicted/scrapy-webdriver
Copyright (c) 2013 Nicolas Cadou, Sosign Interactive
"""

import logging
import time
from threading import Thread, Event
from Queue import Queue, Empty
from twisted.internet import defer, reactor, task
from twisted.python.failure import Failure

from scrapy.exceptions import DontCloseSpider
from scrapy.signals import spider_idle, spider_closed, engine_stopped

from .http import WebdriverRequest, WebdriverActionRequest, WebdriverResponse
from .wrapper import WebdriverWrapper
from ..reqser import add_reqser_handlers


class WebdriverManager(object):
    """Manages the life cycle of a webdriver instance."""

    logger = logging.getLogger(__name__)
    global_manager = None

    wait_sec = 1
    defer_sec = 0
    poll_sec = 1

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.active = 0

        self.wrapper = WebdriverWrapper(crawler.settings)
        self.wrapper.webdriver_loglevel(self.crawler.settings)
        self._webdriver = None

        self._spider = self._url = None
        self.queue = Queue()
        self.spider_done = Event()
        self.spider_done.set()
        self.running = True
        self.thread = Thread(target=self._background_worker)
        self.thread.start()

        self.poll_task = None
        if self.poll_sec > 0:
            # force reactor to check for events periodically
            self.poll_task = task.LoopingCall(self._next_poll)

        self.crawler.signals.connect(self.on_idle, signal=spider_idle)
        self.crawler.signals.connect(self.on_close, signal=spider_closed)
        self.crawler.signals.connect(self.on_stop, signal=engine_stopped)

        assert type(self).global_manager is None, \
            'Attempt to instantiate WebdriverManager twice'
        type(self).global_manager = self

    @property
    def webdriver(self):
        """Return the webdriver instance, instantiate it if necessary."""
        if self._webdriver is None:
            self.logger.debug('Create webdriver browser')
            self._webdriver = self.wrapper.open()
            if self.poll_task:
                self.poll_task.start(self.poll_sec)
        return self._webdriver

    def _next_poll(self):
        pass

    def download_request(self, request, spider):
        """Download a page using webdriver or perform webdriver actions."""
        assert isinstance(request, WebdriverRequest), \
            'Only a WebdriverRequest can use the webdriver instance.'
        deferred = defer.Deferred()
        self.queue.put((request, spider, deferred))
        return deferred

    def _background_worker(self):
        while self.is_active():
            try:
                request, spider, d = self.queue.get(timeout=self.wait_sec)
            except Empty:
                continue
            try:
                if not self.spider_done.is_set():
                    self.logger.debug('Wait: %s', request.url)
                    while not self.spider_done.wait(self.wait_sec):
                        if not self.is_active():
                            raise RuntimeError('Stopped')
                if request.lock:
                    self.spider_done.clear()
                response = self._perform_request(request, spider)
                reactor.callLater(self.defer_sec, d.callback, response)
            except Exception:
                reactor.callLater(self.defer_sec, d.errback, Failure())
                self.release()
        self.on_stop()
        self.logger.debug('Background worker finished')

    def _perform_request(self, request, spider):
        self._spider = spider
        self._url = request.url
        self._inc_stats('webdriver/active')
        self.active += 1
        webdriver = self.webdriver
        if isinstance(request, WebdriverActionRequest):
            self.logger.debug('Actions (lock=%d): %s',
                              request.lock, request.url)
            request.actions.perform()
            self._inc_stats('webdriver/actions')
        else:
            self.logger.debug('Download (lock=%d): %s',
                              request.lock, request.url)
            webdriver.get(request.url)
            self._inc_stats('webdriver/downloads')
        self._inc_stats('webdriver/total')
        return WebdriverResponse(request.url, webdriver)

    def release(self, schedule_next=True):
        self.logger.debug('Release (lock=%d): %s',
                          not self.spider_done.is_set(), self._url)
        self._inc_stats('webdriver/active', -1)
        if self.active > 0:
            self.active -= 1
        self._spider = self._url = None
        self.spider_done.set()
        if schedule_next:
            self.crawler.engine.slot.nextcall.schedule()

    def is_active(self):
        return self.running and self.crawler.crawling

    def _inc_stats(self, key, count=1):
        if self.stats:
            self.stats.inc_value(key, count=count, spider=self._spider)

    @classmethod
    def patch_request_serialization(cls):
        # cls.logger.debug('Patching scrapy request serializers')
        # print 'Patching scrapy request serializers'
        add_reqser_handlers(cls._request_to_dict_handler,
                            cls._request_from_dict_handler)

    @classmethod
    def _request_to_dict_handler(cls, d, request, spider):
        assert not isinstance(request, WebdriverActionRequest), \
            'WebdriverActionRequest serialization is unimplemented for now'
        if isinstance(request, WebdriverRequest):
            d['wd_webdriver'] = 1
            manager = request.manager
            assert cls.global_manager is not None, \
                'WebdriverManager is not active, cannot serialize request'
            assert manager is None or manager == cls.global_manager, \
                'WebdriverRequest must belong with global WebdriverManager'
            d['wd_manager'] = int(manager is not None)
            d['wd_lock'] = int(request.lock)
        return d

    @classmethod
    def _request_from_dict_handler(cls, d, request, spider):
        if not d.get('wd_webdriver', 0):
            return request
        kwargs = {}
        for kw in ('url', 'method', 'headers', 'body', 'cookies', 'encoding',
                   'meta', 'priority', 'dont_filter', 'callback', 'errback'):
            kwargs[kw] = getattr(request, kw)
        if d.get('wd_manager', 0):
            assert cls.global_manager is not None, \
                'WebdriverManager is not active, cannot deserialize request'
            kwargs['manager'] = cls.global_manager
        else:
            kwargs['manager'] = None
        kwargs['lock'] = bool(d.get('wd_lock', 1))
        return WebdriverRequest(**kwargs)

    def on_idle(self):
        if self.active:
            self.logger.debug('Wait for pending requests')
            raise DontCloseSpider

    def on_close(self):
        if self.running:
            self.logger.debug('Stop background task')
            self.running = False

    def on_stop(self):
        self.on_close()
        time.sleep(self.wait_sec)
        if self._webdriver:
            self._webdriver = None
            self.wrapper.close()
        if self.poll_task:
            if self.poll_task.running:
                self.poll_task.stop()
            self.poll_task = None
        if self.active:
            self.logger.warn('Requests dangling on exit')


WebdriverManager.patch_request_serialization()
