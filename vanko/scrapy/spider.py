import os
import sys
import json
import traceback
import shutil
import logging
import urllib

from scrapy import Spider, signals
from scrapy.utils import project, log
from scrapy.settings import default_settings
from twisted.internet import reactor

from .settings import CustomSettings, ACTION_PARAMETER, DEFAULT_ACTION
from .redis import connection as redis_conn
from .mongo import connection as mongo_conn
from .redis.httpcache import RedisCacheStorage
from .mongo.httpcache import MongoCacheStorage
from ..utils import JSONEncoder
from ..utils.misc import getrunid


CustomSettings.register(
    PROXY='',
    SPIDER_FIX_PROXY=True,
    SPIDER_BACKEND_tmpl='%(STORAGE_BACKEND)s',
    UPLOAD_INFO_KEY='%(spider)s:upload-info',
    UPLOAD_INFO_RESET=False,
    )


class CustomSpider(Spider):
    key_field = 'key'

    def __init__(self, *args, **kwargs):
        super(CustomSpider, self).__init__(*args, **kwargs)
        self.action = kwargs.pop(ACTION_PARAMETER, None)
        self.redis = self.mongo = None

    @classmethod
    def update_settings(cls, settings):
        # apply custom settings
        Spider.update_settings(settings)
        custom = CustomSettings(cls.name, settings)
        settings.setdict(custom.as_dict(), custom.priority)
        cls.settings_init = settings

        # reconfigure logging
        logger = logging.root
        logger.removeHandler(logger.handlers[0])
        logger.addHandler(log._get_handler(settings))

    def _set_crawler(self, crawler):
        super(CustomSpider, self)._set_crawler(crawler)
        crawler.signals.connect(self.opened, signals.spider_opened)
        s = self.settings
        self.debug = s.getbool('DEBUG')

        base_action = s.get(ACTION_PARAMETER, DEFAULT_ACTION)
        if getattr(self, 'action', None) is None:
            self.action = base_action
        self.action_list = self.action.split(',')
        if 'settings' in self.action_list:
            self.print_settings(s)

        # reconfigure proxy
        if s.getbool('SPIDER_FIX_PROXY') and self.get_proxy(s) and \
                not os.environ.get('http_proxy'):
            self.logger.debug('Proxy: %s', self.get_proxy())
            os.environ['http_proxy'] = self.get_proxy()

    @staticmethod
    def print_settings(settings):
        print '---------------- Settings ----------------'
        defs = default_settings.__dict__
        for name, opt in sorted(settings.attributes.items()):
            if opt.value != defs.get(name, NotImplemented):
                print '{} = {!r}'.format(name, opt.value)
        print '------------------------------------------'

    def get_proxy(self, settings=None):
        proxy = getattr(self, '_proxy_url', None)
        if proxy is None:
            settings = (settings or getattr(self, 'settings', None) or
                        self.settings_init)
            proxy = settings.get('PROXY', '')
            if not proxy:
                proxy = os.environ.get('http_proxy', '')
            if not proxy and sys.platform == 'win32':
                proxy = (urllib.getproxies_registry() or {}).get('http', '')
            if proxy and '://' not in proxy:
                proxy = 'http://' + proxy
            self._proxy_url = proxy
        return proxy

    def opened(self):
        self.backend = self.settings.get('SPIDER_BACKEND')
        self.upload_info_key = self.settings.get('UPLOAD_INFO_KEY')
        self.encoder = JSONEncoder()
        self.crawler_stopped = False
        self.open_database()

        self._flag_exit = self._flag_stop = True
        for action in self.action_list:
            self._flag_exit = self._flag_stop = False
            self.run_action(action)
        if self._flag_stop:
            reactor.callLater(0, self.crawler.stop)
        if self._flag_exit:
            self.abort(0)

    def closed(self, reason):
        if reason == 'finished':
            self.on_finished()
        else:
            self.close_database()

    def open_database(self):
        if self.backend == 'redis':
            self.redis = redis_conn.from_settings(self.settings)
        if self.backend == 'mongo':
            self.mongo = mongo_conn.from_settings(self.settings)

    def close_database(self):
        self.redis = None
        self.mongo = None

    def reset_database(self):
        pass

    def purge_database(self):
        if self.redis or self.mongo:
            table = self.get_table_name()
        if self.redis and table:
            self.redis.delete(table)
        if self.mongo and table:
            self.mongo[table].delete_many({})

    def get_db(self):
        if self.redis:
            return self.redis
        if self.mongo:
            return self.mongo

    def get_table_name(self, item=None, name_base=None):
        sep = ':' if self.backend == 'redis' else '_'
        name_base = name_base or 'items'
        return getattr(self, 'table_name', self.name + sep + name_base)

    def store_item(self, table, key, data, name_base=None, debug=False):
        if table is None:
            table = self.get_table_name(data, name_base)
        if key is None:
            key = self.get_next_key(table)
        if debug is None:
            debug = self.debug
        if self.redis:
            self.redis.hset(table, key, self.encoder.encode(data))
        if self.mongo:
            data[self.key_field] = key
            if debug:
                data['_run'] = getrunid()
            self.mongo[table].update_one(
                {self.key_field: key}, {'$set': data}, upsert=True)

    def get_next_key(self, table=None, name_base=None):
        table = table or self.get_table_name(name_base=name_base)
        assert self.redis or self.mongo, 'No table for next key'
        if self.redis:
            return self.redis.hlen(table) + 1
        if self.mongo:
            return self.mongo[table].count() + 1

    def _process_store_item(self, item):
        process = getattr(self, 'process_store_item', None)
        if not process:
            return
        result = process(item)
        if result is None:
            return
        if not isinstance(result, (tuple, list)):
            result = [result]

        num = len(result)
        assert 1 <= num <= 3, 'Invalid result of process_store_item()'
        if num == 3:
            table, key, data = result
        elif num == 2:
            key, data = result
            table = self.get_table_name(data)
        elif num == 1:
            data = result[0]
            table = self.get_table_name(data)
            key = self.get_next_key(table)

        if key is not None:
            self.store_item(table, key, data)

    def upload_info(self, op, key, data=None):
        if not self.upload_info_key:
            return
        if op == 'get':
            data = self.redis.hget(self.upload_info_key, key)
            if data is not None:
                return json.loads(data)
        if op == 'set':
            self.redis.hset(self.upload_info_key, key, json.dumps(data))

    def reset_scheduler(self):
        s = self.settings
        tables = []
        key = s.get('SCHEDULER_QUEUE_TABLE')
        if key:
            tables.extend((key, key + '-url'))
        key = s.get('SCHEDULER_DUPEFILTER_TABLE')
        if key:
            tables.extend((key, key + '-url'))

        if self.upload_info_key and s.getbool('UPLOAD_INFO_RESET'):
            tables.append(self.upload_info_key)

        backend = s.get('SCHEDULER_BACKEND')
        ss_url = s.get('SCHEDULER_STORAGE_URL')

        if backend == 'mongo' and tables:
            self.logger.debug(
                'Deleting mongo tables: %s', ', '.join(tables))
            db = mongo_conn.from_settings(ss_url)
            for table in tables:
                db[table].delete_many({})

        if backend == 'redis' and tables:
            self.logger.debug('Deleting redis keys: %s', ', '.join(tables))
            redis = redis_conn.from_settings(ss_url)
            redis.delete(*tables)

    def clear_cache(self, what=''):
        s = self.settings
        enabled = (s.getbool('HTTPCACHE_ENABLED') and s.get('HTTPCACHE_TABLE'))
        backend = s.get('HTTPCACHE_BACKEND')
        if what in ('redis', 'all') and enabled and backend == 'redis':
            RedisCacheStorage.clear_all(self)
        if what in ('mongo', 'all') and enabled and backend == 'mongo':
            MongoCacheStorage.clear_all(self)
        if what in ('disk', 'all'):
            for subdir in '', self.settings['HTTPCACHE_DIR']:
                path = os.path.join(project.data_path(subdir), self.name)
                self.logger.debug('Removing %s', path)
                shutil.rmtree(path, ignore_errors=True)

    def finish(self, message=None, stop=False, exit=True):
        self.logger.info(message or 'Done')
        if stop:
            self._flag_stop = True
        if exit:
            self._flag_exit = True

    def stop_crawler(self, message=None, reason='finished'):
        if not self.crawler_stopped:
            self.crawler.engine.close_spider(self, reason='finished')
            if message:
                self.logger.info(message)
            self.crawler_stopped = True

    def abort(self, ret=1):
        os._exit(ret)

    def run_action(self, action):
        self.logger.debug('Action: %s', action)
        try:
            method = getattr(self, 'on_' + action)
        except AttributeError:
            self.logger.error('Action unimplemented: %s', action)
            self.abort(1)
        try:
            method()
        except Exception:
            traceback.print_exc()
            self.abort(1)

    def on_all(self):
        self.on_reset(exit=False)
        self.run_action('crawl')

    def on_finished(self):
        self.close_database()

    def on_reset(self, exit=True, message='State cleared'):
        self.reset()
        self.reset_database()
        self.reset_scheduler()
        self.crawler.stats.clear_stats(self)
        self.finish(message, stop=exit, exit=exit)

    def reset(self):
        pass

    def on_purge(self, exit=True):
        self.purge()
        self.clear_cache('all')
        self.purge_database()
        self.on_reset(exit, message='Data purged')

    def purge(self):
        pass

    def on_settings(self, exit=True):
        self.finish('Bye', stop=exit, exit=exit)

    def on_crawl(self):
        pass

    def on_excel(self):
        pass

    def on_parse(self):
        pass

    def on_shell(self):
        pass
