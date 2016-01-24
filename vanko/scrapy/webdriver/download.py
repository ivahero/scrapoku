"""
This source code is based on the scrapy_webdriver project located at
  https://github.com/brandicted/scrapy-webdriver
Copyright (c) 2013 Nicolas Cadou, Sosign Interactive
"""

from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from .http import WebdriverRequest


class WebdriverDownloadHandler(object):
    """This download handler uses webdriver, deferred in a thread.
    Falls back to the stock scrapy download handler for non-webdriver requests.
    """
    def __init__(self, settings):
        self._enabled = bool(settings.get('WEBDRIVER_BROWSER'))
        self._fallback_handler = HTTPDownloadHandler(settings)

    def download_request(self, request, spider):
        """Return the result of the right download method for the request."""
        if self._enabled and isinstance(request, WebdriverRequest):
            return request.manager.download_request(request, spider)
        else:
            return self._fallback_handler.download_request(request, spider)
