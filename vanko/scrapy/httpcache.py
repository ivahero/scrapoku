import os
import logging
from time import time
from scrapy.extensions.httpcache import FilesystemCacheStorage
from .settings import CustomSettings

CustomSettings.register_map(
    'httpcachestorage',
    normal='scrapy.extensions.httpcache.FilesystemCacheStorage',
    files='vanko.scrapy.httpcache.SFTPCacheStorage',
    redis='vanko.scrapy.redis.httpcache.RedisCacheStorage',
    mongo='vanko.scrapy.mongo.httpcache.MongoCacheStorage',
    )

CustomSettings.register_map(
    'httpcacheurl',
    normal='',
    files='',
    redis='%(REDIS_URL)s',
    mongo='%(MONGODB_URL)s',
    )

CustomSettings.register_map(
    'httpcachetable',
    normal='',
    files='',
    redis='%(spider)s:httpcache',
    mongo='%(spider)s_httpcache',
    )

CustomSettings.register(
    HTTPCACHE_ENABLED=True,
    HTTPCACHE_COMPRESS=True,
    HTTPCACHE_COMPRESSLEVEL=6,
    HTTPCACHE_EXPIRATION_SECS=0,
    HTTPCACHE_DEBUG=False,
    HTTPCACHE_BACKEND_tmpl='%(STORAGE_BACKEND)s',  # normal,files,redis,mongo
    HTTPCACHE_STORAGE_tmpl_map_httpcachestorage='%(HTTPCACHE_BACKEND)s',
    HTTPCACHE_STORAGE_URL_tmpl_map_httpcacheurl='%(HTTPCACHE_BACKEND)s',
    HTTPCACHE_TABLE_tmpl_map_httpcachetable='%(HTTPCACHE_BACKEND)s',
    HTTPCACHE_SFTP_tmpl='',
    HTTPCACHE_METADATA=[],
    )


class FilesystemCacheStorage2(FilesystemCacheStorage):
    logger = logging.getLogger(__name__)
    response_items = ['meta', 'pickled_meta',
                      'response_headers', 'response_body',
                      'request_headers', 'request_body']

    def __init__(self, settings):
        super(FilesystemCacheStorage2, self).__init__(settings)
        self.debug = settings.getbool('DEBUG')

    def retrieve_response(self, spider, request):
        res = super(FilesystemCacheStorage2,
                    self).retrieve_response(spider, request)
        if self.debug:
            rpath = self._get_request_path(spider, request)
            age = -1
            if os.path.exists(os.path.join(rpath, 'pickled_meta')):
                try:
                    age = time() - os.stat(rpath).st_mtime
                except IOError:
                    pass
            self.logger.debug(
                'Cache %(state)s (%(age)d > %(exp)d): %(url)s under: %(path)s',
                dict(state='HIT' if res else 'MISS', url=request.url,
                     path=rpath, age=age, exp=self.expiration_secs))
        return res

    def store_response(self, spider, request, response):
        super(FilesystemCacheStorage2,
              self).store_response(spider, request, response)
