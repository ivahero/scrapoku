from time import time
from scrapy.dupefilters import BaseDupeFilter
from scrapy.utils.request import request_fingerprint
from . import connection
from ...utils.misc import getrunid


class RFPDupeFilter(BaseDupeFilter):
    """Mongo-based request duplication filter"""
    debug = False

    def __init__(self, db, table):
        self.table = db[table]
        self.table.create_index('fp', background=True)
        self.debug = type(self).debug

    @classmethod
    def from_settings(cls, settings):
        db = connection.from_settings(settings)
        table = 'dupefilter_%d' % int(time())
        return cls(db, table)

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def request_seen(self, request):
        fp = request_fingerprint(request)
        if self.table.find_one(dict(fp=fp)):
            return True
        record = {'fp': fp}
        if self.debug:
            record['_url'] = request.url
            record['_run'] = getrunid()
        self.table.insert(record)
        return False

    def close(self, reason):
        """Delete data on close. Called by scrapy's scheduler"""
        self.clear()

    def clear(self):
        """Clears fingerprints data"""
        self.table.delete_many({})
