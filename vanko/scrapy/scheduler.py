"""
This source code is based on the scrapy_redis project located at
  https://github.com/rolando/scrapy-redis
Copyright (c) Rolando Espinoza La fuente
All rights reserved.
"""

import logging
from scrapy.utils.misc import load_object
from .settings import CustomSettings
from .reqser import request_is_serializable


CustomSettings.register_map(
    'scheduler',
    normal='scrapy.core.scheduler.Scheduler',
    files='vanko.scrapy.scheduler.PersistentScheduler',
    redis='vanko.scrapy.scheduler.PersistentScheduler',
    mongo='vanko.scrapy.scheduler.PersistentScheduler',
    )

CustomSettings.register_map(
    'ssclass',
    normal='vanko.scrapy.scheduler.DummyStorage',
    files='vanko.scrapy.scheduler.DummyStorage',
    redis='vanko.scrapy.redis.connection.from_settings',
    mongo='vanko.scrapy.mongo.connection.from_settings',
    )

CustomSettings.register_map(
    'ssurl',
    normal='',
    files='',
    redis='%(REDIS_URL)s',
    mongo='%(MONGODB_URL)s',
    )

CustomSettings.register_map(
    'sqtable',
    normal='',
    files='',
    redis='%(spider)s:scheduler-queue',
    mongo='%(spider)s_scheduler_queue'
    )

CustomSettings.register_map(
    'sqclass',
    normal='%(SCHEDULER_QUEUE_CLASS_NORMAL)s',
    files='%(SCHEDULER_QUEUE_CLASS_FILES)s',
    redis='%(SCHEDULER_QUEUE_CLASS_REDIS)s',
    mongo='%(SCHEDULER_QUEUE_CLASS_MONGO)s',
    )

CustomSettings.register_map(
    'sdftable',
    normal='',
    files='',
    redis='%(spider)s:dupefilter-set',
    mongo='%(spider)s_dupefilter_set',
    )

CustomSettings.register_map(
    'sdfclass',
    normal='scrapy.dupefilters.RFPDupeFilter',
    files='scrapy.dupefilters.RFPDupeFilter',
    redis='vanko.scrapy.redis.dupefilter.RFPDupeFilter',
    mongo='vanko.scrapy.mongo.dupefilter.RFPDupeFilter',
    )

CustomSettings.register(
    SCHEDULER_BACKEND_tmpl='%(STORAGE_BACKEND)s',  # normal,files,redis,mongo
    SCHEDULER_PERSIST=True,
    SCHEDULER_IDLE_BEFORE_CLOSE=0.5,
    SCHEDULER_DEBUG=False,
    SCHEDULER_tmpl_map_scheduler='normal',
    SCHEDULER_tmpl_map_scheduler_on_crawl='%(SCHEDULER_BACKEND)s',
    SCHEDULER_STORAGE_CLASS_tmpl_map_ssclass='%(SCHEDULER_BACKEND)s',
    SCHEDULER_STORAGE_URL_tmpl_map_ssurl='%(SCHEDULER_BACKEND)s',
    SCHEDULER_QUEUE_TABLE_tmpl_map_sqtable='%(SCHEDULER_BACKEND)s',
    SCHEDULER_QUEUE_CLASS_tmpl_map_sqclass='%(SCHEDULER_BACKEND)s',
    SCHEDULER_QUEUE_CLASS_NORMAL='scrapy.squeues.LifoMemoryQueue',
    SCHEDULER_QUEUE_CLASS_FILES='scrapy.squeues.PickleLifoDiskQueue',
    SCHEDULER_QUEUE_CLASS_REDIS='vanko.scrapy.redis.queue.SpiderPriorityQueue',
    SCHEDULER_QUEUE_CLASS_MONGO='vanko.scrapy.mongo.queue.SpiderPriorityQueue',
    SCHEDULER_QUEUE_NONSER_CLASS_tmpl='scrapy.squeues.LifoMemoryQueue',
    SCHEDULER_DUPEFILTER_TABLE_tmpl_map_sdftable='%(SCHEDULER_BACKEND)s',
    SCHEDULER_DUPEFILTER_CLASS_tmpl_map_sdfclass='%(SCHEDULER_BACKEND)s',
    SCHEDULER_DUPEFILTER_NONSER_CLASS_tmpl='scrapy.dupefilters.RFPDupeFilter',
    )


class PersistentScheduler(object):
    """Redis/Mongo/Files-based scheduler"""

    logger = logging.getLogger(__name__.rpartition('.')[2])
    # logger.setLevel(logging.INFO)

    def __init__(self, backend, storage_cls, storage_url,
                 persist, idle_before_close, debug,
                 queue_table, queue_cls, queue_nonser_cls,
                 dfilter_table, dfilter_cls, dfilter_nonser_cls):
        self.backend = backend
        self.storage_cls = storage_cls
        self.storage_url = storage_url
        self.persist = persist
        self.idle_before_close = idle_before_close
        self.debug = debug
        self.queue_table = queue_table
        self.queue_cls = queue_cls
        self.queue_nonser_cls = queue_nonser_cls
        self.dfilter_table = dfilter_table
        self.dfilter_cls = dfilter_cls
        self.dfilter_nonser_cls = dfilter_nonser_cls
        self.stats = None

    @classmethod
    def from_settings(cls, settings):
        return cls(
            backend=settings.get('SCHEDULER_BACKEND'),
            storage_cls=load_object(
                settings.get('SCHEDULER_STORAGE_CLASS')),
            storage_url=settings.get('SCHEDULER_STORAGE_URL'),
            persist=settings.getbool('SCHEDULER_PERSIST'),
            idle_before_close=settings.getfloat('SCHEDULER_IDLE_BEFORE_CLOSE'),
            debug=settings.getbool('SCHEDULER_DEBUG'),
            queue_table=settings.get('SCHEDULER_QUEUE_TABLE'),
            queue_cls=load_object(settings.get('SCHEDULER_QUEUE_CLASS')),
            queue_nonser_cls=load_object(
                settings.get('SCHEDULER_QUEUE_NONSER_CLASS')),
            dfilter_table=settings.get('SCHEDULER_DUPEFILTER_TABLE'),
            dfilter_cls=load_object(
                settings.get('SCHEDULER_DUPEFILTER_CLASS')),
            dfilter_nonser_cls=load_object(
                settings.get('SCHEDULER_DUPEFILTER_NONSER_CLASS')),
            )

    @classmethod
    def from_crawler(cls, crawler):
        scheduler = cls.from_settings(crawler.settings)
        # FIXME: for now, stats are only supported from this constructor
        scheduler.stats = crawler.stats
        return scheduler

    def open(self, spider):
        self.spider = spider
        self.storage = self.storage_cls(self.storage_url)
        self.queue_cls.debug = self.debug
        self.queue = self.queue_cls(
            self.storage, spider, self.queue_table % dict(spider=spider.name))
        self.queue_nonser = self.queue_nonser_cls()
        self.dfilter_cls.debug = self.debug
        self.dfilter = self.dfilter_cls(
            self.storage, self.dfilter_table % dict(spider=spider.name))
        self.dfilter_nonser = self.dfilter_nonser_cls()
        if self.idle_before_close < 0:
            self.idle_before_close = 0
        if len(self.queue):
            spider.logger.info('Resuming crawl (%d requests scheduled)'
                               % len(self.queue))

    def close(self, reason):
        if not self.persist:
            self.dfilter.clear()
            self.queue.clear()

    def enqueue_request(self, request):
        if not request_is_serializable(request):
            if not request.dont_filter and \
                    self.dfilter_nonser.request_seen(request):
                return
            if self.stats:
                self.stats.inc_value('scheduler/enqueued/nonser',
                                     spider=self.spider)
            self.queue_nonser.push(request)
            self.logger.debug('enqueue (unser) %s', request)
            return

        if not request.dont_filter and self.dfilter.request_seen(request):
            # self.logger.debug('seen %s', request)
            return

        if self.stats:
            self.stats.inc_value('scheduler/enqueued/%s' % self.backend,
                                 spider=self.spider)

        self.logger.debug('enqueue %s', request)
        self.queue.push(request)

    def next_request(self):
        request = self.queue_nonser.pop()
        if request is not None:
            self.self.logger.debug('next nonser %s', request)
            if self.stats:
                self.stats.inc_value('scheduler/dequeued/nonser',
                                     spider=self.spider)
            return request
        block_pop_timeout = self.idle_before_close
        request = self.queue.pop(block_pop_timeout)
        if request and self.stats:
            self.stats.inc_value('scheduler/dequeued/%s' % self.backend,
                                 spider=self.spider)
        self.logger.debug('next %s', request)
        return request

    def __len__(self):
        return len(self.queue)

    def has_pending_requests(self):
        return len(self) > 0


class DummyStorage(object):
    def __init__(self, url):
        pass
