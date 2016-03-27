import logging
from scrapy.core.downloader import Downloader
from scrapy.core.downloader.handlers.http import HTTPDownloadHandler

logger = logging.getLogger('CustomDownloader')
logger.setLevel(logging.INFO)


class CustomDownloader(Downloader):
    def __init__(self, crawler):
        # logger.debug('init')
        super(CustomDownloader, self).__init__(crawler)

    def needs_backout(self):
        # logger.debug('n/r %s < %s', len(self.active), self.total_concurrency)
        return len(self.active) >= self.total_concurrency

    def fetch(self, request, spider):
        # logger.debug('fetch %s', request)
        return super(CustomDownloader, self).fetch(request, spider)

    def _enqueue_request(self, request, spider):
        # logger.debug('enqueue %s', request)
        return super(CustomDownloader, self)._enqueue_request(request, spider)

    def _process_queue(self, spider, slot):
        return super(CustomDownloader, self)._process_queue(spider, slot)

    def _download(self, slot, request, spider):
        # logger.debug('download started: %s', request)
        dfd = super(CustomDownloader, self)._download(slot, request, spider)

        def _response_downloaded(response):
            # logger.debug('response downloaded: %s', response)
            return response

        dfd.addCallback(_response_downloaded)
        return dfd


class CustomHTTPDownloadHandler(HTTPDownloadHandler):
    def __init__(self, settings):
        super(CustomHTTPDownloadHandler, self).__init__(settings)

    def download_request(self, request, spider):
        return super(CustomHTTPDownloadHandler,
                     self).download_request(request, spider)
