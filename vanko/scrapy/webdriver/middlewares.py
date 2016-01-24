"""
This source code is based on the scrapy_webdriver project located at
  https://github.com/brandicted/scrapy-webdriver
Copyright (c) 2013 Nicolas Cadou, Sosign Interactive
"""

import logging
from scrapy.exceptions import NotConfigured

from .http import WebdriverActionRequest, WebdriverRequest
from .manager import WebdriverManager
from .. import CustomSettings


CustomSettings.register(
    DOWNLOAD_HANDLERS={
        'http': 'vanko.scrapy.webdriver.download.WebdriverDownloadHandler',
        'https': 'vanko.scrapy.webdriver.download.WebdriverDownloadHandler',
        },
    SPIDER_MIDDLEWARES={
        'vanko.scrapy.webdriver.middlewares.WebdriverSpiderMiddleware': 543,
        },
    WEBDRIVER_ACTION_REQUEST_PRIORITY_ADJUST=100,
    )


class WebdriverSpiderMiddleware(object):
    """Coordinates concurrent webdriver access."""

    logger = logging.getLogger(__name__)

    def __init__(self, crawler):
        if not crawler.settings.get('WEBDRIVER_BROWSER'):
            raise NotConfigured
        self.manager = WebdriverManager(crawler)
        self.action_priority_adjust = crawler.settings.getint(
            'WEBDRIVER_ACTION_REQUEST_PRIORITY_ADJUST')

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def process_start_requests(self, start_requests, spider):
        """Return start requests with reordering."""
        return self._process_requests(start_requests, start=True)

    def process_spider_output(self, response, result, spider):
        """Return spider result, with requests reordered."""
        for item_or_request in self._process_requests(result, start=False):
            yield item_or_request
        if isinstance(response.request, WebdriverRequest):
            response.request.manager.release()

    def _process_requests(self, items_or_requests, start=False):
        action_requests = []
        download_requests = []
        for request in iter(items_or_requests):
            if not isinstance(request, WebdriverRequest):
                yield request
                continue
            if isinstance(request, WebdriverActionRequest):
                if start:
                    self.logger.warning(
                        'Ignore start WebdriverActionRequest: %s', request.url)
                    continue
                request = request.replace(
                    manager=self.manager,
                    priority=request.priority + self.action_priority_adjust)
                action_requests.append(request)
            else:
                download_requests.append(request.replace(manager=self.manager))
        for request in action_requests:
            yield request
        for request in download_requests:
            yield request
