import logging
from ..stats import PersistentStatsCollector
from . import connection


class RedisStatsCollector(PersistentStatsCollector):
    DEFAULT_STATS_TABLE = '%(spider)s:stats'
    DEFAULT_STATS_REDIS_URL = 'redis://localhost'
    logger = logging.getLogger('.'.join(__name__.split('.')[-2:]))

    def __init__(self, crawler):
        s = crawler.settings
        self._redis = connection.from_settings(
            s.get('STATS_STORAGE_URL', self.DEFAULT_STATS_REDIS_URL))
        self._name = s.get('STATS_TABLE', self.DEFAULT_STATS_TABLE)
        self._hash = None
        self._dump = s.getbool('STATS_DUMP')
        self._starters = {}

    def open_spider(self, spider):
        self._hash = self._name % {'spider': spider.name}

    def close_spider(self, spider, reason):
        if self._dump:
            self.dump_stats(spider)

    def get_value(self, key, default=None, spider=None):
        val = self._redis.hget(self._hash, key)
        return default if val is None else float(val)

    def get_stats(self, spider=None):
        return self._redis.hgetall(self._hash)

    def set_value(self, key, value, spider=None):
        self._redis.hset(self._hash, key, value)

    def set_stats(self, stats, spider=None):
        self._redis.delete(self._hash)
        for key, val in stats.iteritems():
            self._redis.hset(self._hash, key, val)

    def inc_value(self, key, count=1, start=0, spider=None):
        if self._hash is None:
            return
        if start != self._starters.get(key, 0):
            self._starters[key] = start
            self._redis.hsetnx(self._hash, key, start)
        self._redis.hincrby(self._hash, key, count)

    def max_value(self, key, value, spider=None):
        val = self._redis.hget(self._hash, key)
        if val is None or val < value:
            self._redis.hset(self._hash, key, value)

    def min_value(self, key, value, spider=None):
        val = self._redis.hget(self._hash, key)
        if val is None or val > value:
            self._redis.hset(self._hash, key, value)

    def clear_stats(self, spider=None):
        self._redis.delete(self._hash)
