from __future__ import print_function, absolute_import
import logging
from scrapy import signals
from scrapy.settings import Settings
from scrapy.crawler import CrawlerProcess
from . import defs


def qwebkit_settings(settings=None):
    if settings is None:
        settings = Settings()
    elif settings.getbool('__WT__'):
        return settings
    else:
        settings = settings.copy()
        settings.frozen = False
    for name in dir(defs):
        if name.startswith('WT_') and settings.get(name) is None:
            settings.set(name, getattr(defs, name))
    settings.set('__WT__', True)
    return settings


def _on_stopped(_=None, __=None):
    from .handlers import QtWebkitCrawlerPool

    if QtWebkitCrawlerPool.has_visible():
        logging.info('Crawling finished. Please close windows.')
    else:
        logging.info('Crawling finished. Exiting.')
        try:
            from twisted.internet import reactor
            reactor.stop()
        except RuntimeError:
            pass


def auto_stop_crawling(runner_or_crawler=None):
    if hasattr(runner_or_crawler, 'crawlers') or 1:
        crawlers = runner_or_crawler.crawlers
    else:
        crawlers = [runner_or_crawler]
    for crawler in crawlers:
        crawler.signals.connect(_on_stopped, signal=signals.engine_stopped)


def patch_crawler_process():
    CrawlerProcess._stop_reactor = _on_stopped
