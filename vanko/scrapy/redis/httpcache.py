import logging
from time import time
from six.moves import cPickle as pickle
from cStringIO import StringIO
from gzip import GzipFile
from scrapy.extensions.httpcache import DbmCacheStorage
from . import connection


class RedisCacheStorage(DbmCacheStorage):
    DEFAULT_HTTPCACHE_TABLE = '%(spider)s:httpcache'
    DEFAULT_HTTPCACHE_REDIS_URL = 'redis://localhost'
    logger = logging.getLogger('.'.join(__name__.split('.')[-2:]))

    def __init__(self, settings):
        s = settings
        self.redis = connection.from_settings(s.get(
            'HTTPCACHE_STORAGE_URL', self.DEFAULT_HTTPCACHE_REDIS_URL))
        self.key_tmpl = s.get('HTTPCACHE_TABLE', self.DEFAULT_HTTPCACHE_TABLE)
        self.expiration_secs = s.getint('HTTPCACHE_EXPIRATION_SECS', 0)
        self.compress = s.getbool('HTTPCACHE_COMPRESS', False)
        self.compresslevel = s.getint('HTTPCACHE_COMPRESSLEVEL', 6)
        self.debug = s.getbool('HTTPCACHE_DEBUG', False)

    def open_spider(self, spider):
        key = self.key_tmpl % {'spider': spider.name}
        self.data_hash = '%s-data' % key
        self.time_hash = '%s-time' % key
        self.url_hash = '%s-url' % key if self.debug else None
        self.logger.debug('Redis cache opened')

    def close_spider(self, spider):
        pass

    def store_response(self, spider, request, response):
        key = self._request_key(request)
        data = dict(
            status=response.status,
            url=response.url,
            headers=dict(response.headers),
            body=response.body,
            )
        ts = str(time())
        data = pickle.dumps(data, protocol=2)
        if self.compress:
            iobuf = StringIO()
            iobuf.write('gz~')
            with GzipFile('', 'wb', self.compresslevel, iobuf) as gzip:
                gzip.write(data)
            gzdata = iobuf.getvalue()
            iobuf.close()
            if len(gzdata) < len(data):
                data = gzdata
        self.redis.hset(self.data_hash, key, data)
        self.redis.hset(self.time_hash, key, ts)
        if self.url_hash:
            self.redis.hset(self.url_hash, key, response.url)
        self.logger.debug('Store %s in redis cache', response.url)

    def _read_data(self, spider, request):
        key = self._request_key(request)
        ts = self.redis.hget(self.time_hash, key)
        if ts is None:
            return  # not found
        if 0 < self.expiration_secs < time() - float(ts):
            return  # expired
        data = self.redis.hget(self.data_hash, key)
        if data is None:
            return  # key is dropped
        if data.startswith('gz~'):
            iobuf = StringIO(data)
            iobuf.read(3)
            with GzipFile('', 'rb', self.compresslevel, iobuf) as gzip:
                data = gzip.read()
            iobuf.close()
        data = pickle.loads(data)
        self.logger.debug('Retrieve %s from redis cache', data['url'])
        return data

    def _clear(self):
        self.redis.delete(self.time_hash, self.data_hash)
        if self.url_hash:
            self.redis.delete(self.url_hash)

    @classmethod
    def clear_all(cls, spider):
        cache = cls(spider.crawler.settings)
        cache.open_spider(spider)
        cache._clear()
