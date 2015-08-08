from __future__ import print_function, absolute_import
import scrapy
import re
import logging
from collections import deque
from scrapy.http import HtmlResponse
from scrapy.utils.misc import load_object
from scrapy.exceptions import NotSupported
from scrapy.utils.decorators import inthread
from twisted.internet import defer
from twisted.internet import reactor
from twisted.internet import threads
from .qt4webkit import QtCrawler
from .utils import qwebkit_settings, patch_crawler_process


if map(int, scrapy.version_info) < [0, 18]:
    FALLBACK_HANDLER = 'http.HttpDownloadHandler'
elif map(int, scrapy.version_info) >= [0, 24, 4]:
    FALLBACK_HANDLER = 'http.HTTPDownloadHandler'
else:
    FALLBACK_HANDLER = 'http10.HTTP10DownloadHandler'
FALLBACK_HANDLER = 'scrapy.core.downloader.handlers.%s' % FALLBACK_HANDLER


class QtWebkitCrawlerPool(object):

    _instance = None

    def __init__(self, settings=None):
        self.crawlers = [deque(), deque()]
        self.waiters = [deque(), deque()]
        self.stats = [0, 0]
        settings = qwebkit_settings(settings)
        self.limits = [
            settings.getint('WT_HIDE_POOL_SIZE'),
            settings.getint('WT_SHOW_POOL_SIZE')
        ]
        for show in (0, 1):
            for i in xrange(self.limits[show]):
                self.crawlers[show].append(QtCrawler(show=show))
        if settings.getbool('WT_PATCH_CRAWLER_PROCESS'):
            patch_crawler_process()

    @classmethod
    def get_instance(cls, settings=None):
        if cls._instance is None:
            cls._instance = cls(settings)
        return cls._instance

    @classmethod
    def has_visible(cls):
        return cls.get_instance().stats[1] > 0

    def get_crawler(self, show=False):
        show = int(show)
        if self.limits[show] < 1:
            msg = 'Please configure WT_%s_POOL_SIZE properly' \
                  % ['HIDE', 'SHOW'][show]
            raise NotSupported(msg)
        self.stats[show] += 1
        try:
            return defer.succeed(self.crawlers[show].popleft())
        except IndexError:
            waiter = defer.Deferred()
            self.waiters[show].append(waiter)
            return waiter

    def return_crawler(self, crawler):
        show = int(crawler.is_shown())
        try:
            waiter = self.waiters[show].popleft()
            reactor.callLater(0, lambda: waiter.callback(crawler))
        except IndexError:
            self.crawlers[show].append(crawler)


class QtWebkitDownloadHandler(object):

    REQUEST_ARGS = [
            ('scroll_timeout', int,  0,     None),
            ('max_height',     int,  0,     None),
            ('page_timeout',   int,  None,  'WT_PAGE_TIMEOUT'),
            ('proxy',          str,  '',    None),
            ('user_agent',     str,  '',    None),
            ('qwebkit',        int,  0,     None),
            ('verbose',        int,  None,  'WT_VERBOSE'),
            ('show',           int,  None,  'WT_SHOW'),
        ]

    def __init__(self, settings=None):
        self.settings = qwebkit_settings(settings)
        self.pool = QtWebkitCrawlerPool.get_instance(self.settings)
        self.fallback_handler = load_object(FALLBACK_HANDLER)(self.settings)

    def download_request(self, request, spider):
        if request.meta.get('qwebkit') \
                or re.search(r'%5Bqwebkit=[1-9]\d*%5D', request.url) \
                or self.settings.getbool('WT_FORCE_QCRAWLER'):
            if self.settings.getbool('WT_THREADED_DOWNLOAD'):
                handler = self._download_inthread
            else:
                handler = self._download_inline
        else:
            handler = self.fallback_handler.download_request
        return handler(request, spider)

    @inthread
    def _download_inthread(self, request, spider):
        self.verbose = self.extract_request_params(request)['verbose']
        self.log(request.url, 'before blocking call')
        result = threads.blockingCallFromThread(
            reactor, self._download_inline, request, spider)
        self.log(request.url, 'after blocking call')
        return result

    @defer.inlineCallbacks
    def _download_inline(self, request, spider):
        kwargs = self.extract_request_params(request)
        self.verbose = kwargs['verbose']
        self.log(request.url, 'kwargs: %r' % kwargs)
        url = kwargs['url']

        self.log(url, 'getting crawler (show=%s)' % kwargs['show'])
        crawler = yield self.pool.get_crawler(kwargs['show'])
        self.log(url, 'start crawling with %s' % crawler.get_id())
        result = yield crawler.crawl(kwargs)
        self.log(url, 'analyzing results of %s' % crawler.get_id())

        body = result.get('body', u'').encode('utf-8')
        headers = self.convert_response_headers(result.get('headers'))

        response = HtmlResponse(url, body=body, headers=headers)
        self.log(url, 'returning crawler %s' % crawler.get_id())
        self.pool.return_crawler(crawler)
        defer.returnValue(response)

    def extract_request_params(self, request):
        args = self.REQUEST_ARGS[:]
        url = request.url
        kwargs = dict()
        found = True

        while found:
            found = False
            for ptuple in args:
                param, ptype, defval, setting = ptuple
                if defval is None and setting is not None:
                    defval = self.settings.get(setting)
                kwargs[param] = request.meta.get(param, defval)
                mo = re.search('%5B' + param + '=(\\w+)%5D$', url)
                if mo:
                    kwargs[param] = ptype(mo.group(1))
                    url = url[:mo.start()]
                    found = True
                    args.remove(ptuple)

        kwargs['url'] = url
        return kwargs

    def convert_response_headers(self, response_headers):
        headers = dict()

        for key, vals in response_headers:
            if key == 'Set-Cookie':
                if isinstance(vals, basestring):
                    vals = vals.split('\n')
            else:
                key = '__' + key
                if isinstance(vals, basestring):
                    vals = [vals]
            for val in vals:
                if key not in headers:
                    headers[key] = val
                elif isinstance(headers[key], list):
                    headers[key].append(val)
                else:
                    headers[key] = [headers[key], val]

        for key in headers:
            if key.startswith('__'):
                del headers[key]

        return headers

    def log(self, url, msg):
        if self.verbose:
            logging.debug('[%s] downloader: %s' % (url, msg))
