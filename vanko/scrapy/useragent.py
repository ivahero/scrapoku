import re
import logging
import pkgutil
from random import randint
from scrapy import signals

from .settings import CustomSettings

CustomSettings.register_map(
    'uastorageurl',
    normal='',
    files='',
    redis='%(REDIS_URL)s',
    mongo='%(MONGODB_URL)s',
    )

CustomSettings.register_map(
    'uastoragetable',
    normal='',
    files='',
    redis='%(spider)s:useragent-seq',
    mongo='%(spider)s_useragent_seq',
    )

CustomSettings.register(
    USERAGENT_ENABLED=True,
    USERAGENT_RANDOM=-1,
    USERAGENT_FIXED='',
    USERAGENT_BACKEND_tmpl='%(STORAGE_BACKEND)s',  # normal,files,redis,mongo
    USERAGENT_STORAGE_URL_tmpl_map_uastorageurl='%(USERAGENT_BACKEND)s',
    USERAGENT_STORAGE_TABLE_tmpl_map_uastoragetable='%(USERAGENT_BACKEND)s',
    )


class PersistentUserAgentMiddleware(object):
    """This downloader middleware rotates user agent on each restart"""

    logger = logging.getLogger(__name__.rpartition('.')[2])
    _singleton = None

    def __init__(self, settings):
        self.settings = settings
        self.enabled = settings.getbool('USERAGENT_ENABLED')
        self.backend = settings.get('USERAGENT_BACKEND')
        self.storage_url = settings.get('USERAGENT_STORAGE_URL')
        self.storage_table = settings.get('USERAGENT_STORAGE_TABLE')
        self.fixed_ua = settings.get('USERAGENT_FIXED')

        randomize = settings.getint('USERAGENT_RANDOM')
        if randomize < 0:
            self.randomize = self.backend not in ('redis', 'mongo')
        else:
            self.randomize = bool(randomize)

        self._ua_list = None
        self._user_agent = None
        type(self)._singleton = self

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.settings)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    @classmethod
    def get_global_user_agent(cls, spider):
        return cls._singleton.get_user_agent(spider)

    def get_ua_list(self):
        if self._ua_list is None:
            ua_list = self.settings.getlist('USERAGENT_LIST', [])
            if not ua_list:
                data = pkgutil.get_data(__package__, 'useragent.xml')
                for line in data.splitlines():
                    mo = re.search(r'useragent="([^"]+)"', line)
                    if mo:
                        ua_list.append(mo.group(1).strip())
            self._ua_list = ua_list
            self.logger.debug('Pulled %d user agents', len(ua_list))

        return self._ua_list

    def _get_table_name(self, spider):
        name = self.storage_table
        if '%(spider)s' in name:
            assert spider, 'get_user_agent() requires a spider!'
            name = name % dict(spider=spider.name)
        return name

    def _incr_redis_index(self, spider):
        from .redis import connection
        redis = connection.from_settings(self.storage_url)
        key = self._get_table_name(spider)
        result = redis.incr(key)
        redis.connection_pool.disconnect()
        return int(result)

    def _incr_mongo_index(self, spider):
        from .mongo import connection
        db = connection.from_settings(self.storage_url)
        table = self._get_table_name(spider)
        result = db[table].find_one_and_update(
            {}, {'$inc': dict(seq=1)}, return_document=True, upsert=True)
        db.client.close()
        return int(result['seq'])

    def _incr_stored_index(self, spider):
        try:
            if self.backend == 'redis':
                return self._incr_redis_index(spider)
            if self.backend == 'mongo':
                return self._incr_mongo_index(spider)
        except Exception as err:
            self.logger.info('Cannot get User-Agent from redis: %s', err)

    def get_user_agent(self, spider=None):
        if self.enabled and self._user_agent is None:
            ua_list = self.get_ua_list()
            ua_num = len(ua_list)
            randomize = self.randomize
            if not randomize:
                index = self._incr_stored_index(spider)
                if index is None:
                    randomize = True
            if randomize:
                index = randint(0, ua_num)
            random_ua = ua_list[(index + ua_num - 1) % ua_num]
            self._user_agent = getattr(spider, 'user_agent',
                                       self.fixed_ua or random_ua)

        return self._user_agent

    def spider_opened(self, spider):
        user_agent = self.get_user_agent(spider)
        if user_agent:
            self.logger.info('User-Agent: %s', user_agent)

    def process_request(self, request, spider):
        user_agent = self.get_user_agent()
        if user_agent:
            request.headers.setdefault('User-Agent', user_agent)
