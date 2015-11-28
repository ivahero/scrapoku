import time
from scrapy import signals
from scrapy.pipelines.files import FilesPipeline
from scrapy.utils.misc import md5sum
from twisted.internet import threads

from ..utils.sftp import SFTPClient
from . import CustomSettings

CustomSettings.register(
    IMAGES_STORE_tmpl='%(images_dir)s',
    MIRROR_STORE_tmpl='%(mirror_dir)s',
    )


class SFTPFilesStore(object):

    def __init__(self, url):
        assert url.startswith('sftp://')
        self.sftp = SFTPClient(url)
        self.bg = 'bg=1' in self.sftp.options
        self.spiders = {}

    def _close_spider(self, spider):
        self.spiders.pop(spider.name, None)
        if not self.spiders:
            self.sftp.close()

    def _open_spider(self, info):
        spider = info.spider
        if spider.name not in self.spiders:
            self.spiders[spider.name] = spider
            spider.crawler.signals.connect(self._close_spider,
                                           signals.spider_closed)
        return spider

    def stat_file(self, path, info):
        spider = self._open_spider(info)
        upload_info_func = getattr(spider, 'upload_info')
        if upload_info_func:
            data = upload_info_func('get', path)
            if isinstance(data, (list, tuple)) and len(data) == 2:
                return {'last_modified': data[0], 'checksum': data[1]}
        return {}  # catching everything

    def persist_file(self, path, buf, info, meta=None, headers=None):
        spider = self._open_spider(info)
        upload_info_func = getattr(spider, 'upload_info')

        def upload_buffer():
            buf.seek(0)
            self.sftp.upload_buffer(path, buf)
            if upload_info_func:
                buf.seek(0)
                upload_info_func('set', path, [time.time(), md5sum(buf)])
            buf.seek(0)

        if self.bg:
            return threads.deferToThread(upload_buffer)
        else:
            upload_buffer()


FilesPipeline.STORE_SCHEMES['sftp'] = SFTPFilesStore
