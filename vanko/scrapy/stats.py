from pprint import pformat
from .settings import CustomSettings


CustomSettings.register_map(
    'statsclass',
    normal='scrapy.statscollectors.MemoryStatsCollector',
    files='scrapy.statscollectors.MemoryStatsCollector',
    redis='vanko.scrapy.redis.stats.RedisStatsCollector',
    mongo='vanko.scrapy.mongo.stats.MongoStatsCollector',
    )

CustomSettings.register_map(
    'statsurl',
    normal='',
    files='',
    redis='%(REDIS_URL)s',
    mongo='%(MONGODB_URL)s',
    )

CustomSettings.register_map(
    'statstable',
    normal='',
    files='',
    redis='%(spider)s:stats',
    mongo='%(spider)s_stats',
    )

CustomSettings.register(
    STATS_BACKEND_tmpl='%(STORAGE_BACKEND)s',
    STATS_CLASS_tmpl_map_statsclass='%(STATS_BACKEND)s',
    STATS_STORAGE_URL_tmpl_map_statsurl='%(STATS_BACKEND)s',
    STATS_TABLE_tmpl_map_statstable='%(STATS_BACKEND)s',
    STATS_DUMP=False,
    )


class PersistentStatsCollector(object):
    def dump_stats(self, spider):
        self.logger.info('Dumping Scrapy stats:\n' + pformat(self.get_stats()),
                         extra={'spider': spider})
