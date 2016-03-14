import logging
from time import time, sleep
from datetime import datetime
from ..reqser import request_to_dict2, request_from_dict2
from ...utils.misc import getrunid

__all__ = ['SpiderQueue', 'SpiderPriorityQueue', 'SpiderStack']


class Base(object):
    """Per-spider queue/stack base class"""
    poll_minsec = 0.2
    poll_maxsec = 2.0
    poll_factor = 1.4
    index_keys = []
    debug = False

    logger = logging.getLogger('.'.join(__name__.split('.')[-2:]))
    logger.setLevel(logging.INFO)

    def __init__(self, db, spider, table):
        self.spider = spider
        self.table = db[table % dict(spider=spider.name)]
        self.table.create_index(self.index_keys, background=True)
        self.debug = type(self).debug

    def __len__(self):
        return self.table.count()

    def push(self, request):
        """Push a request"""
        record = request_to_dict2(request, self.spider)
        record['_ts'] = datetime.utcnow()
        if self.debug:
            record['_run'] = getrunid()
        self.table.insert_one(record)
        self.logger.debug('push %s', request)

    def pop(self, timeout=0):
        """Pop a request"""
        endtime = time() + timeout
        poll_sec = self.poll_minsec
        while 1:
            record = self.table.find_one_and_delete(
                {}, sort=self.index_keys,
                projection=dict(_id=False, _ts=False, _run=False))
            if record:
                request = request_from_dict2(record, self.spider)
                self.logger.debug('pop (t=%s) %s', timeout, request)
                return request
            curtime = time()
            if curtime >= endtime:
                self.logger.debug('pop (t=%s) None', timeout)
                return
            sleep(min(poll_sec, endtime - curtime))
            poll_sec = min(poll_sec * self.poll_factor, self.poll_maxsec)

    def clear(self):
        """Clear queue/stack"""
        self.table.delete_many({})


class SpiderQueue(Base):
    """Per-spider FIFO queue"""
    index_keys = [('_ts', 1)]


class SpiderPriorityQueue(Base):
    """Per-spider priority queue"""
    index_keys = [('priority', -1), ('_ts', -1)]


class SpiderStack(Base):
    """Per-spider stack"""
    index_keys = [('_ts', -1)]
