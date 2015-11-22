import os
import logging
import requests
from scrapy import signals


class ShowIP(object):
    logger = logging.getLogger(__name__.rpartition('.')[2])

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def __init__(self, crawler):
        if crawler.settings.getbool('HEROKU', True):
            crawler.signals.connect(self.spider_opened, signals.spider_opened)

    def spider_opened(self, spider):
        self.logger.info('Spider IP address: %s', self.get_ip())

    @classmethod
    def get_ip(cls, proxies=None):
        proxies = cls.get_proxies(proxies)
        res = requests.get('http://httpbin.org/ip', proxies=proxies)
        try:
            ip = res.json()['origin']
        except Exception:
            ip = None
        return ip

    @classmethod
    def get_proxies(cls, proxies=None):
        if proxies is None:
            proxies = {}
            proxy = os.environ.get('http_proxy', '')
            if proxy:
                proxies['http'] = proxy
            proxy = os.environ.get('https_proxy', '')
            if proxy:
                proxies['https'] = proxy
            if not proxies:
                proxies = None
        return proxies
