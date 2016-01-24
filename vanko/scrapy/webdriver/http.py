"""
This source code is based on the scrapy_webdriver project located at
  https://github.com/brandicted/scrapy-webdriver
Copyright (c) 2013 Nicolas Cadou, Sosign Interactive
"""

from scrapy.http import Request, TextResponse
from selenium.webdriver.common.action_chains import ActionChains
from .response import WebdriverResponseMixin


class WebdriverRequest(Request):
    """A Request needed when using the webdriver download handler."""

    def __init__(self, url, manager=None, lock=True, **kwargs):
        super(WebdriverRequest, self).__init__(url, **kwargs)
        self.manager = manager
        self.lock = lock

    def replace(self, *args, **kwargs):
        kwargs.setdefault('manager', self.manager)
        kwargs.setdefault('lock', self.lock)
        return super(WebdriverRequest, self).replace(*args, **kwargs)


class WebdriverActionRequest(WebdriverRequest):
    """A Request that handles in-page webdriver actions (action chains)."""

    def __init__(self, response, actions=None, **kwargs):
        kwargs.setdefault('manager', response.request.manager)
        url = kwargs.pop('url', response.request.url)
        super(WebdriverActionRequest, self).__init__(url, **kwargs)
        self._response = response
        self.actions = actions or response.actions
        self.parent = response.request

    def replace(self, *args, **kwargs):
        kwargs.setdefault('response', self._response)
        kwargs.setdefault('actions', self.actions)
        return super(WebdriverActionRequest, self).replace(*args, **kwargs)


class WebdriverResponse(WebdriverResponseMixin, TextResponse):
    """A Response that will feed the webdriver page into its body."""
    def __init__(self, url, webdriver, **kwargs):
        kwargs.setdefault('body', webdriver.page_source)
        kwargs.setdefault('encoding', 'utf-8')
        super(WebdriverResponse, self).__init__(url, **kwargs)
        self.actions = ActionChains(webdriver)
        self.webdriver = webdriver

    def action_request(self, **kwargs):
        """Return a Request object to perform the recorded actions."""
        kwargs.setdefault('meta', self.meta)
        return WebdriverActionRequest(self, **kwargs)
