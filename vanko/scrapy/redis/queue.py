"""
This source code is based on the scrapy_redis project located at
  https://github.com/rolando/scrapy-redis
Copyright (c) Rolando Espinoza La fuente
All rights reserved.
"""

from ..reqser import request_to_dict2, request_from_dict2

try:
    import cPickle as pickle
except ImportError:
    import pickle

__all__ = ['SpiderQueue', 'SpiderPriorityQueue', 'SpiderStack']


class Base(object):
    """Per-spider queue/stack base class"""
    debug = False

    def __init__(self, server, spider, key):
        """Initialize per-spider redis queue.

        Parameters:
            server -- redis connection
            spider -- spider instance
            key -- key for this queue (e.g. "%(spider)s:queue")
        """
        self.server = server
        self.spider = spider
        self.key = key % dict(spider=spider.name)
        self.debug = type(self).debug
        self.url_key = self.key + '-url' if self.debug else None

    def _encode_request(self, request):
        """Encode a request object"""
        return pickle.dumps(request_to_dict2(request, self.spider),
                            protocol=-1)

    def _decode_request(self, encoded_request):
        """Decode an request previously encoded"""
        return request_from_dict2(pickle.loads(encoded_request), self.spider)

    def __len__(self):
        """Return the length of the queue"""
        raise NotImplementedError

    def push(self, request):
        """Push a request"""
        raise NotImplementedError

    def pop(self, timeout=0):
        """Pop a request"""
        raise NotImplementedError

    def clear(self):
        """Clear queue/stack"""
        self.server.delete(self.key)
        if self.url_key:
            self.server.delete(self.url_key)


class SpiderQueue(Base):
    """Per-spider FIFO queue"""

    def __len__(self):
        """Return the length of the queue"""
        return self.server.llen(self.key)

    def push(self, request):
        """Push a request"""
        self.server.lpush(self.key, self._encode_request(request))
        if self.url_key:
            self.server.lpush(self.url_key, request.url)

    def pop(self, timeout=0):
        """Pop a request"""
        if timeout > 0:
            data = self.server.brpop(self.key, timeout)
            if isinstance(data, tuple):
                data = data[1]
        else:
            data = self.server.rpop(self.key)
        if data:
            if self.url_key:
                self.server.rpop(self.url_key)
            return self._decode_request(data)


class SpiderPriorityQueue(Base):
    """Per-spider priority queue abstraction using redis' sorted set"""

    def __len__(self):
        """Return the length of the queue"""
        return self.server.zcard(self.key)

    def push(self, request):
        """Push a request"""
        data = self._encode_request(request)
        pairs = {data: -request.priority}
        self.server.zadd(self.key, **pairs)

    def pop(self, timeout=0):
        """
        Pop a request
        timeout not support in this queue class
        """
        # use atomic range/remove using multi/exec
        pipe = self.server.pipeline()
        pipe.multi()
        pipe.zrange(self.key, 0, 0).zremrangebyrank(self.key, 0, 0)
        results, count = pipe.execute()
        if results:
            return self._decode_request(results[0])


class SpiderStack(Base):
    """Per-spider stack"""

    def __len__(self):
        """Return the length of the stack"""
        return self.server.llen(self.key)

    def push(self, request):
        """Push a request"""
        self.server.lpush(self.key, self._encode_request(request))
        if self.url_key:
            self.server.lpush(self.url_key, request.url)

    def pop(self, timeout=0):
        """Pop a request"""
        if timeout > 0:
            data = self.server.blpop(self.key, timeout)
            if isinstance(data, tuple):
                data = data[1]
        else:
            data = self.server.lpop(self.key)

        if data:
            if self.url_key:
                self.server.lpop(self.url_key)
            return self._decode_request(data)
