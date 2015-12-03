import os
import logging
from twisted.internet.threads import deferToThread
from .httpcache import FilesystemCacheStorage2

try:
    from ..utils.sftp import SFTPClient
except ImportError:
    SFTPClient = None


class SFTPCacheStorage(FilesystemCacheStorage2):
    logger = logging.getLogger(__name__)

    def __init__(self, settings):
        super(SFTPCacheStorage, self).__init__(settings)
        self.sftp_cli = None
        self.sftp_url = settings.get('HTTPCACHE_SFTP')
        if self.sftp_url:
            assert self.sftp_url.startswith('sftp://'), \
                'Invalid SFTP URL: %s' % self.sftp_url
            assert SFTPClient is not None, \
                'ImportError: vanko.scrapy.utils.SFTPClient'

    def open_spider(self, spider):
        super(SFTPCacheStorage, self).open_spider(spider)
        if self.sftp_url:
            self.sftp_cli = SFTPClient(self.sftp_url,
                                       local_dir=self.cachedir)
            self.sftp_bg = 'bg=1' in self.sftp_cli.options

    def close_spider(self, spider):
        super(SFTPCacheStorage, self).close_spider(spider)
        if self.sftp_cli:
            self.sftp_cli.close()

    def store_response(self, spider, request, response):
        super(SFTPCacheStorage, self).store_response(spider, request, response)
        if self.sftp_cli:
            rpath = self._get_request_path(spider, request)
            if self.sftp_bg:
                return deferToThread(self._upload_items, rpath)
            else:
                self._upload_items(rpath)

    def _upload_items(self, rpath):
        for item in self.response_items:
            self.sftp_cli.upload_file(os.path.join(rpath, item))
