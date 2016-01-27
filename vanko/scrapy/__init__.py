# flake8: noqa
from .defaults import DEFAULT_PROJECT_DIR
try:
    import scrapy
    del scrapy
except ImportError:
    pass
else:
    from .helpers import setup_spider, run_spider, setup_stderr
    from .settings import CustomSettings
    from .spider import CustomSpider
    from .crawl import CustomCrawlSpider
    from .item_loader import (
        TFItemLoader, TakeFirstItemLoader, Item, SimpleItem,
        Field, IdentityField, StripField, JoinField, DateTimeField)
    from .fast_exit import FastExit
    from .show_ip import ShowIP
    from .restart_on import RestartOn
    from .redis.httpcache import RedisCacheStorage
    from .mongo.httpcache import MongoCacheStorage
    from .httpcache import FilesystemCacheStorage2
    from .useragent import PersistentUserAgentMiddleware
    from .pipelines import ItemStorePipeline, EarlyProcessPipeline
    from .scheduler import PersistentScheduler
    from .stats import PersistentStatsCollector
