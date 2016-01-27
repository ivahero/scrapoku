"""
This source code is based on the scrapy_redis project located at
  https://github.com/rolando/scrapy-redis
Copyright (c) Rolando Espinoza La fuente
All rights reserved.
"""

import six
import types
from scrapy import Spider
from scrapy.utils.misc import load_object

from . import connection
from .dupefilter import RFPDupeFilter

# default values
SCHEDULER_PERSIST = False
QUEUE_KEY = '%(spider)s:requests'
QUEUE_CLASS = 'vanko.scrapy.redis.queue.SpiderPriorityQueue'
DUPEFILTER_KEY = '%(spider)s:dupefilter'
IDLE_BEFORE_CLOSE = 0


class Scheduler(object):
    """Redis-based scheduler"""

    def __init__(self, server, persist, queue_key, queue_cls, dupefilter_key,
                 idle_before_close, unser_df, unser_queue_cls):
        """Initialize scheduler.

        Parameters
        ----------
        server : Redis instance
        persist : bool
        queue_key : str
        queue_cls : queue class
        dupefilter_key : str
        idle_before_close : int
        """
        self.server = server
        self.persist = persist
        self.queue_key = queue_key
        self.queue_cls = queue_cls
        self.dupefilter_key = dupefilter_key
        self.idle_before_close = idle_before_close
        self.stats = None
        self.unser_df = unser_df
        self.unser_queue_cls = unser_queue_cls

    def __len__(self):
        return len(self.queue)

    @classmethod
    def from_settings(cls, settings):
        persist = settings.get('SCHEDULER_PERSIST', SCHEDULER_PERSIST)
        queue_key = settings.get('SCHEDULER_QUEUE_KEY', QUEUE_KEY)
        queue_cls = load_object(settings.get('SCHEDULER_QUEUE_CLASS',
                                             QUEUE_CLASS))
        dupefilter_key = settings.get('DUPEFILTER_KEY', DUPEFILTER_KEY)
        idle_before_close = settings.get('SCHEDULER_IDLE_BEFORE_CLOSE',
                                         IDLE_BEFORE_CLOSE)
        server = connection.from_settings(settings)
        unser_dupefilter_cls = load_object(settings['DUPEFILTER_CLASS'])
        unser_df = unser_dupefilter_cls.from_settings(settings)
        unser_queue_cls = load_object(settings.get('SCHEDULER_MEMORY_QUEUE'))
        return cls(server, persist, queue_key, queue_cls, dupefilter_key,
                   idle_before_close, unser_df, unser_queue_cls)

    @classmethod
    def from_crawler(cls, crawler):
        instance = cls.from_settings(crawler.settings)
        # FIXME: for now, stats are only supported from this constructor
        instance.stats = crawler.stats
        return instance

    def open(self, spider):
        self.spider = spider
        self.queue = self.queue_cls(self.server, spider, self.queue_key)
        self.df = RFPDupeFilter(self.server,
                                self.dupefilter_key % {'spider': spider.name})
        self.unser_queue = self.unser_queue_cls()
        if self.idle_before_close < 0:
            self.idle_before_close = 0
        # notice if there are requests already in the queue to resume the crawl
        if len(self.queue):
            spider.log('Resuming crawl (%d requests scheduled)'
                       % len(self.queue))

    def close(self, reason):
        if not self.persist:
            self.df.clear()
            self.queue.clear()

    def enqueue_request(self, request):
        if not request_is_serializable(request):
            if not request.dont_filter and self.unser_df.request_seen(request):
                return
            if self.stats:
                self.stats.inc_value('scheduler/enqueued/unser',
                                     spider=self.spider)
            self.unser_queue.push(request)
            return

        if not request.dont_filter and self.df.request_seen(request):
            return
        if self.stats:
            self.stats.inc_value('scheduler/enqueued/redis',
                                 spider=self.spider)
        self.queue.push(request)

    def next_request(self):
        request = self.unser_queue.pop()
        if request is not None:
            if self.stats:
                self.stats.inc_value('scheduler/dequeued/unser',
                                     spider=self.spider)
            return request
        block_pop_timeout = self.idle_before_close
        request = self.queue.pop(block_pop_timeout)
        if request and self.stats:
            self.stats.inc_value('scheduler/dequeued/redis',
                                 spider=self.spider)
        return request

    def has_pending_requests(self):
        return len(self) > 0


def request_is_serializable(request):
    for cb in request.callback, request.errback:
        if cb is None or isinstance(cb, basestring):
            continue
        if isinstance(cb, types.MethodType):
            obj = six.get_method_self(cb)
            if not isinstance(obj, Spider):
                return False
            func = six.get_method_function(cb)
            attr = getattr(obj, func.__name__, None)
            if callable(attr):
                continue
        if isinstance(cb, types.FunctionType) and cb.__name__.isalnum():
            continue
        return False
    return True
