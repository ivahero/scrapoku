import sys

if __name__ == '__main__':
    from PyQt4 import QtGui
    global_app = QtGui.QApplication([])
    import qt4reactor
    qt4reactor.install()

    # from twisted.internet import reactor
    # from scrapy.utils.log import configure_logging
    # from scrapy.settings import Settings
    # from .utils import auto_stop_crawling
    # from .handlers import QtWebkitDownloadHandler, QtWebkitCrawlerPool
    # from .qt4webkit import QtCrawler

    from scrapy import crawler
    from scrapy.utils.project import get_project_settings

    cprocess = crawler.CrawlerProcess(get_project_settings())
    cprocess.crawl(sys.argv[1])
    cprocess.start()
