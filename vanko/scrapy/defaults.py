import os

DEFAULT_BOT_NAME = 'scrapybot'
DEFAULT_PROJECT_DIR = os.path.join(os.path.expanduser('~'), '.vanko')
DEFAULT_SCRAPY_DIR = os.path.join(DEFAULT_PROJECT_DIR, 'scrapy')
DEFAULT_LOG_DIR = os.path.join(DEFAULT_PROJECT_DIR, 'logs')
ACTION_PARAMETER = 'ACTION'
ACTION_ARGUMENT = '--action='
PARAM_ARGUMENT = '--param='
DEFAULT_ACTION = 'crawl'
INITIAL_CWD = os.getcwd()

CUSTOM_SETTINGS = dict(
    LOG_LEVEL='INFO',
    LOG_FORMAT=('%(asctime)s.%(msecs)03d (%(process)d) [%(name)s] '
                '%(levelname)s: %(message)s'),
    AUTOTHROTTLE_ENABLED=False,
    AUTOTHROTTLE_DEBUG=False,

    ACTION=DEFAULT_ACTION,
    DEBUG=False,
    HEROKU=False,

    STORAGE_BACKEND='normal',  # normal, files, redis, mongo
    REDIS_URL='redis://localhost',
    MONGODB_URL='mongodb://localhost/test',

    DOWNLOADER='vanko.scrapy.downloader.CustomDownloader',
    DOWNLOAD_HANDLERS={
        'http': 'vanko.scrapy.downloader.CustomHTTPDownloadHandler',
        'https': 'vanko.scrapy.downloader.CustomHTTPDownloadHandler',
        's3': None,  # fixes boto error "cannot read instance data"
        },
    DOWNLOADER_MIDDLEWARES={
        'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
        'vanko.scrapy.PersistentUserAgentMiddleware': 400,
        },
    EXTENSIONS={
        'vanko.scrapy.FastExit': 0,
        'vanko.scrapy.RestartOn': 0,
        'vanko.scrapy.ShowIP': 0,
        },
    )
