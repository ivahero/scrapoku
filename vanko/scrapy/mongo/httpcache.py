import logging
from datetime import datetime
from cStringIO import StringIO
from gzip import GzipFile
from scrapy.extensions.httpcache import DbmCacheStorage
from . import connection
from ...utils.misc import getrunid


class MongoCacheStorage(DbmCacheStorage):
    DEFAULT_HTTPCACHE_TABLE = '%(spider)s_httpcache'
    DEFAULT_HTTPCACHE_MONGODB_URL = 'mongodb://localhost/test'
    logger = logging.getLogger('.'.join(__name__.split('.')[-2:]))

    def __init__(self, settings):
        s = settings
        self.db = connection.from_settings(s.get(
            'HTTPCACHE_STORAGE_URL', self.DEFAULT_HTTPCACHE_MONGODB_URL))
        self.table_tpl = s.get('HTTPCACHE_TABLE', self.DEFAULT_HTTPCACHE_TABLE)
        self.expiration_secs = s.getint('HTTPCACHE_EXPIRATION_SECS', 0)
        self.compress = s.getbool('HTTPCACHE_COMPRESS', False)
        self.compresslevel = s.getint('HTTPCACHE_COMPRESSLEVEL', 6)
        self.metadata = s.getlist('HTTPCACHE_METADATA', [])
        self.encoding = 'iso-8859-1'

    def open_spider(self, spider):
        self.coll = self.db[self.table_tpl % {'spider': spider.name}]
        self.coll.create_index('key', unique=True, background=True)
        self.coll.create_index('url', background=True)
        self.coll.create_index('ts', background=True)
        self.coll.create_index('status', background=True)
        self.logger.debug('MongoDB cache opened')

    def close_spider(self, spider):
        pass

    def store_response(self, spider, request, response):
        record = dict(
            key=self._request_key(request),
            status=response.status,
            url=response.url,
            headers=dict(response.headers),
            body=response.body,
            gzbody='',
            ts=datetime.utcnow(),
            _run=getrunid(),
            )

        if self.metadata and request.meta:
            rmeta = request.meta
            _meta = {f: rmeta[f] for f in self.metadata if f in rmeta}
            if _meta:
                record['_meta'] = _meta

        if self.compress:
            iobuf = StringIO()
            with GzipFile('', 'wb', self.compresslevel, iobuf) as gzip:
                gzip.write(record['body'])
            gzbody = iobuf.getvalue()
            iobuf.close()
            if len(gzbody) < len(record['body']):
                record['body'] = ''
                record['gzbody'] = gzbody

        self._dict_to_unicode(record)
        self._dict_to_unicode(record['headers'])

        self.coll.update_one({'key': record['key']}, {'$set': record},
                             upsert=True)
        self.logger.debug('Store %s in mongodb cache', response.url)

    def _read_data(self, spider, request):
        key = self._request_key(request)
        record = self.coll.find_one({'key': key},
                                    projection={'_id': 0, 'key': 0, '_run': 0})
        if not record:
            return  # not found
        record_age = (datetime.utcnow() - record['ts']).total_seconds()
        if 0 < self.expiration_secs < record_age:
            return  # expired
        self.logger.debug('Retrieve %s from mongodb cache', record['url'])

        self._dict_from_unicode(record)
        self._dict_from_unicode(record['headers'])

        if record.get('gzbody', '') and not record.get('body', ''):
            iobuf = StringIO(record['gzbody'])
            with GzipFile('', 'rb', self.compresslevel, iobuf) as gzip:
                record['body'] = gzip.read()
                record['gzbody'] = ''
            iobuf.close()

        return record

    def _dict_to_unicode(self, d):
        encoding = self.encoding
        for key, val in d.items():
            if val and isinstance(val, str):
                d[key] = val.decode(encoding)

    def _dict_from_unicode(self, d):
        encoding = self.encoding
        for key, val in d.items():
            if isinstance(val, unicode):
                d[key] = val.encode(encoding)

    def _clear(self):
        self.coll.delete_many({})

    @classmethod
    def clear_all(cls, spider):
        cache = cls(spider.crawler.settings)
        cache.open_spider(spider)
        cache._clear()
