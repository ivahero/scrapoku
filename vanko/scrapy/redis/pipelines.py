"""
This source code is based on the scrapy_redis project located at
  https://github.com/rolando/scrapy-redis
Copyright (c) Rolando Espinoza La fuente
All rights reserved.
"""

from twisted.internet.threads import deferToThread
from . import connection
from ..utils import JSONEncoder


class RedisPipeline(object):
    """Pushes serialized item into a redis list/queue"""

    def __init__(self, server):
        self.server = server
        self.encoder = JSONEncoder()

    @classmethod
    def from_settings(cls, settings):
        server = connection.from_settings(settings)
        return cls(server)

    @classmethod
    def from_crawler(cls, crawler):
        return cls.from_settings(crawler.settings)

    def process_item(self, item, spider):
        return deferToThread(self._process_item, item, spider)

    def _process_item(self, item, spider):
        key = self.item_key(item, spider)
        data = self.encoder.encode(item)
        self.server.rpush(key, data)
        return item

    def item_key(self, item, spider):
        """Returns redis key based on given spider"""
        return "%s:items" % spider.name
