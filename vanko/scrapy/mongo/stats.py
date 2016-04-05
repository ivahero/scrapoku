import logging
from ..stats import PersistentStatsCollector
from . import connection


class MongoStatsCollector(PersistentStatsCollector):
    DEFAULT_STATS_MONGODB_URL = 'mongodb://localhost/test'
    DEFAULT_STATS_TABLE = '%(spider)s_stats'
    logger = logging.getLogger('.'.join(__name__.split('.')[-2:]))

    def __init__(self, crawler):
        s = crawler.settings
        self._db = connection.from_settings(
            s.get('STATS_STORAGE_URL', self.DEFAULT_STATS_MONGODB_URL))
        self._name = s.get('STATS_TABLE', self.DEFAULT_STATS_TABLE)
        self._coll = None
        self._dump = s.getbool('STATS_DUMP')
        self._starters = {}

    def open_spider(self, spider):
        self._coll = self._db[self._name % {'spider': spider.name}]
        self._coll.create_index('key', background=True)

    def close_spider(self, spider, reason):
        if self._dump:
            self.dump_stats(spider)

    def get_value(self, key, default=None, spider=None):
        return (self._coll.find_one({'key': key}) or {}).get('val', default)

    def get_stats(self, spider=None):
        return {r['key']: r.get('val', 0)
                for r in self._coll.find({}) if 'key' in r}

    def set_value(self, key, value, spider=None):
        self._coll.update_one(
            {'key': key}, {'$set': {'val': value}}, upsert=True)

    def set_stats(self, stats, spider=None):
        self._coll.delete_many({})
        self._coll.insert_many({'key': k, 'val': v} for k, v in stats.items())

    def inc_value(self, key, count=1, start=0, spider=None):
        if self._coll is None:
            return
        if start != self._starters.get(key, 0):
            self._starters[key] = start
            self._coll.update_one(
                {'key': key}, {'$setOnInsert': {'val': start}}, upsert=True)
        self._coll.update_one(
            {'key': key}, {'$inc': {'val': count}}, upsert=True)

    def max_value(self, key, value, spider=None):
        self._coll.update_one(
            {'key': key}, {'$max': {'val': value}}, upsert=True)

    def min_value(self, key, value, spider=None):
        self._coll.update_one(
            {'key': key}, {'$min': {'val': value}}, upsert=True)

    def clear_stats(self, spider=None):
        self._coll.delete_many({})
