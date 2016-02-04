import os
import sys
import json
import logging

from datetime import datetime, timedelta
from functools import wraps
from urllib2 import urlopen
from flask import current_app, request, make_response, Response
from time import time, sleep
from zlib import adler32
from urlparse import urljoin
from mimetypes import guess_type
from flask import g
from flask._compat import text_type
from werkzeug.datastructures import Headers
from werkzeug.wsgi import wrap_file

from ..utils import decode_userpass, as_list


DEFAULT_FORMAT = '%(asctime)s [%(levelname)s]: %(message)s'
BASIC_AUTH_PARAM = 'BASIC_AUTH_SIMPLE'
DEFAULT_CACHE_TIMEOUT = 3600
DEFAULT_APP_PREFIX = 'default_app'


def as_choices(result):
    return [(x, x) for x in as_list(result)]


def setup_flask_logger(app, format=DEFAULT_FORMAT):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(format))
    app.logger.addHandler(handler)
    debug = app.config.get('DEBUG', False)
    app.logger.setLevel(logging.DEBUG if debug else logging.INFO)


def requires_basic_auth(func):
    # Based on flask snippet http://flask.pocoo.org/snippets/8/
    username, passwd = decode_userpass(current_app.config[BASIC_AUTH_PARAM])
    if username and passwd:
        @wraps(func)
        def decorated(*args, **kwargs):
            auth = request.authorization
            if auth and auth.username == username and auth.password == passwd:
                return func(*args, **kwargs)
            return Response(
                'Please login with proper credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'})
        return decorated
    return func


def nocache(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        resp = make_response(func(*args, **kwargs))
        resp.cache_control.no_cache = True
        return resp
    return decorated


def datacache(key, func, args=(), timeout=None,  # core parameters
              # call with key=None to perform a special action:
              #   func=callable   - return uncached value
              #   func='cleanup'  - clear cache
              #   func='discover' - just run storage discovery
              _discovered_storage=None,          # returns chosen storage

              # storage parameters:
              redis=None, redis_key=None,        # redis based cache
              mongodb=None, mongodb_table=None,  # mongodb based cache
              memcache={},                       # memory cache (default)

              # auto-discovery parameters:
              app=None,    # flask application for configuration and storage
              flask=None,  # can be: auto, redis, mongodb, memcache or None
              ):

    # helper functions
    def _value():
        try:
            data = func(*args)
            return data, True
        except StopIteration, e:
            data = e.args[0] if getattr(e, 'args', None) else None
            return data, False

    def _config(name, default):
        try:
            _app = app  # or current_app..
            if _app:
                return _app.config.get(name, default)
        except RuntimeError:
            pass
        return default

    def _global(name):
        try:
            return getattr(g, name, None)
        except RuntimeError:
            try:
                return getattr(app or current_app, name, None)
            except RuntimeError:
                return None

    def _discover(name, value):
        if _discovered_storage is not None:
            _discovered_storage[name] = value

    # start main function
    assert callable(func) or func in ('clear', 'discover'), \
        'func must be a callable or one of: cleanup discover'

    # special mode: directly return uncached value
    if key is None and callable(func):
        return _value()[0]

    # detect whether we use flask for storage discovery
    assert app is None or flask is not None, \
        'Please provide flask argument when app is provided'
    assert flask in (None, False) or app is not None, \
        'Please provide app argument when flask is enabled'
    if flask is True:
        flask = _config('DATACACHE_STORAGE', 'auto')
    assert flask in (None, False, 'auto', 'redis', 'mongodb', 'memcache'), \
        'Invalid flask, must be one of: bool auto redis mongodb memcache'

    # setup timing values
    if timeout is None:
        timeout = int(_config('DATACACHE_TIMEOUT', DEFAULT_CACHE_TIMEOUT))
    utc = datetime.utcnow()
    cur_stamp = utc.strftime('%Y-%m-%dT%H:%M:%S')
    end_stamp = (
        utc - timedelta(seconds=timeout)).strftime('%Y-%m-%dT%H:%M:%S')
    stamp_key = '%s:stamp' % key
    value_key = '%s:value' % key

    # detect whether redis is used
    if flask in ('redis', 'auto') and not redis:
        redis = _global('redis')
        assert flask == 'auto' or redis, 'Please provide g.redis'
    _discover('redis', redis)

    # redis based cache
    if redis:
        if not redis_key:
            redis_key = _config('DATACACHE_REDIS_KEY', '')
            if not redis_key:
                app_prefix = _config('APP_PREFIX', DEFAULT_APP_PREFIX)
                redis_key = '%s:datacache' % app_prefix

        if callable(func):
            value_stamp = redis.hget(redis_key, stamp_key)
            if value_stamp and value_stamp > end_stamp:
                value = json.loads(redis.hget(redis_key, value_key))
            else:
                value, can_cache = _value()
                if can_cache:
                    redis.hset(redis_key, stamp_key, cur_stamp)
                    redis.hset(redis_key, value_key, json.dumps(value))
            return value
        elif func == 'clear':
            redis.delete(redis_key)
        # fall thru if func == 'discover'

    # detect whether mongodb is used
    if flask in ('mongodb', 'auto') and not mongodb:
        mongodb = _global('mongodb')
        assert flask == 'auto' or mongodb, 'Please provide g.mongodb'
    _discover('mongodb', mongodb)

    # mongodb based cache
    if mongodb or mongodb_table:
        if not mongodb_table:
            mongodb_table = _config('DATACACHE_MONGODB_TABLE', '')
            if not mongodb_table:
                app_prefix = _config('APP_PREFIX', DEFAULT_APP_PREFIX)
                mongodb_table = '%s_datacache' % app_prefix

        if isinstance(mongodb_table, basestring):
            assert mongodb, \
                'Please provide mongodb instance or concrete mongodb table'
            mongodb_table = mongodb[mongodb_table]
            mongodb_table.create_index('key', background=True)

        if callable(func):
            record = mongodb_table.find_one(
                dict(key=key, ts={'$gt': end_stamp}))
            if record:
                value = record['data']
            else:
                value, can_cache = _value()
                if can_cache:
                    record = dict(key=key, ts=cur_stamp, data=value)
                    mongodb_table.update_one(
                        dict(key=key), {'$set': record}, upsert=True)
            return value
        elif func == 'clear':
            mongodb_table.delete_many({})
        # fall thru if func == 'discover'

    # detect whether memcache is used
    if flask in ('memcache', 'auto'):
        memcache = _global('memcache')
        assert flask == 'auto' or memcache is not None, \
            'Please provide g.memcache'
    _discover('memcache', memcache)

    # memory based cache
    if memcache is not None:
        assert isinstance(memcache, dict), 'Memcache must be dict'
        if callable(func):
            value_stamp = memcache.get(stamp_key, '')
            if value_stamp and value_stamp > end_stamp and \
                    value_key in memcache:
                value = memcache[value_key]
            else:
                value, can_cache = _value()
                if can_cache:
                    memcache[stamp_key] = cur_stamp
                    memcache[value_key] = value
            return value
        elif func == 'clear':
            memcache.clear()
        # fall thru if func == 'discover'

    # return uncached value
    if callable(func):
        return _value()[0]


def probe_url(url, timeout=0):
    endtime = time() + timeout
    timeleft = 0.0001
    while timeleft > 0:
        try:
            urlopen(url).close()
            return True
        except IOError:
            pass
        timeleft = endtime - time()
        if timeleft > 0:
            sleep(min(timeleft, 0.2))
    return False


def send_file2(filename_or_fp, mimetype=None, as_attachment=False,
               attachment_filename=None, add_etags=True,
               cache_timeout=None, conditional=False):
    assert isinstance(filename_or_fp, basestring), \
        'Please provide file path as a string'
    filename = filename_or_fp

    if filename is not None and not os.path.isabs(filename):
        filename = os.path.join(current_app.root_path, filename)
    if mimetype is None and (filename or attachment_filename):
        mimetype = guess_type(filename or attachment_filename)[0]
    if mimetype is None:
        mimetype = 'application/octet-stream'

    headers = Headers()

    if as_attachment:
        if attachment_filename is None:
            attachment_filename = os.path.basename(filename)
        headers.add('Content-Disposition', 'attachment',
                    filename=attachment_filename)

    x_accel_mapping = getattr(current_app, 'x_accel_mapping', '')
    if not x_accel_mapping:
        x_accel_mapping = current_app.config.get('X_ACCEL_MAPPING', '')
    if not x_accel_mapping:
        x_accel_mapping = request.headers.get('x-flask-accel-mapping', '')
    if not x_accel_mapping:
        x_accel_mapping = request.headers.get('x-accel-mapping', '')

    assert isinstance(x_accel_mapping, (tuple, list, dict, basestring)), \
        'X_ACCEL_MAPPING must be tuple, list, dict, or str'
    if isinstance(x_accel_mapping, basestring):
        x_accel_mapping = [
            it.strip() for it in x_accel_mapping.split(',') if it.strip()]
    elif isinstance(x_accel_mapping, dict):
        x_accel_mapping = sorted(x_accel_mapping.items())
    elif isinstance(x_accel_mapping, tuple):
        x_accel_mapping = [x_accel_mapping]

    headers['Content-Length'] = os.path.getsize(filename)
    mtime = None
    data = None

    for map_item in x_accel_mapping:
        assert isinstance(map_item, (basestring, tuple)), \
            'X_ACCEL_MAPPING items must be 2-tuples or strings'
        if isinstance(map_item, basestring):
            map_path, map_loc = map_item.split('=')
        else:
            map_path, map_loc = map_item

        if not os.path.isabs(map_path):
            map_path = os.path.join(current_app.root_path, map_path)
        if filename.startswith(map_path):
            file_loc = urljoin(map_loc, filename[len(map_path):])
            headers['X-Accel-Redirect'] = file_loc
            break
    else:
        if current_app.use_x_sendfile:
            headers['X-Sendfile'] = filename
        else:
            fp = open(filename, 'rb')
            mtime = os.path.getmtime(filename)
            data = wrap_file(request.environ, fp)

    rv = current_app.response_class(data, mimetype=mimetype, headers=headers,
                                    direct_passthrough=True)
    if mtime is not None:
        rv.last_modified = int(mtime)

    rv.cache_control.public = True
    if cache_timeout is None:
        cache_timeout = current_app.get_send_file_max_age(filename)
    if cache_timeout is not None:
        rv.cache_control.max_age = cache_timeout
        rv.expires = int(time() + cache_timeout)

    if add_etags and filename is not None:
        rv.set_etag('flask-%s-%s-%s' % (
            os.path.getmtime(filename),
            os.path.getsize(filename),
            adler32(
                filename.encode('utf-8') if isinstance(filename, text_type)
                else filename
            ) & 0xffffffff
        ))
        if conditional:
            rv = rv.make_conditional(request)
            # don't send x-sendfile for servers that ignore 304 for x-sendfile
            if rv.status_code == 304:
                rv.headers.pop('x-sendfile', None)
                rv.headers.pop('x-accel-redirect', None)
    return rv
