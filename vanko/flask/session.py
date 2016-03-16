import cPickle as pickle
from datetime import timedelta, datetime
from random import uniform
from time import sleep
from threading import Thread
from uuid import uuid4
from werkzeug.datastructures import CallbackDict
from flask.sessions import SessionInterface, SessionMixin
from ..scrapy.redis import connection as redis_conn
from ..scrapy.mongo import connection as mongo_conn


DEFAULT_SESSION_TIMEOUT = 86400  # one day
DEFAULT_MONGO_CLEANUP_INTERVAL = 600


class _PersistentSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True
        CallbackDict.__init__(self, initial, on_update)
        self.sid = sid
        self.new = new
        self.modified = False


class _PersistentSessionInterface(SessionInterface):
    serializer = pickle
    session_class = _PersistentSession

    def __init__(self, app=None, timeout=None):
        if app:
            app.session_interface = self
        if timeout is None:
            timeout = DEFAULT_SESSION_TIMEOUT
        self.timeout = timeout

    def generate_sid(self):
        return str(uuid4())

    def get_storage_expiration_time(self, app, session):
        if session.permanent:
            return app.permanent_session_lifetime
        return timedelta(seconds=self.timeout)

    def open_session(self, app, request):
        sid = request.cookies.get(app.session_cookie_name)
        if not sid:
            sid = self.generate_sid()
            return self.session_class(sid=sid, new=True)
        val = self._load_data(sid)
        if val is not None:
            data = self.serializer.loads(val)
            return self.session_class(data, sid=sid)
        return self.session_class(sid=sid, new=True)

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)
        if not session:
            self._delete_data(session.sid)
            if session.modified:
                response.delete_cookie(app.session_cookie_name,
                                       domain=domain)
            return
        storage_exp = self.get_storage_expiration_time(app, session)
        cookie_exp = self.get_expiration_time(app, session)
        val = self.serializer.dumps(dict(session))
        self._save_data(session.sid, val, int(storage_exp.total_seconds()))
        response.set_cookie(app.session_cookie_name, session.sid,
                            expires=cookie_exp, httponly=True,
                            domain=domain)

    def _load_data(self, sid):
        raise NotImplementedError

    def _save_data(self, sid, data, expire):
        raise NotImplementedError

    def _delete_data(self, sid):
        raise NotImplementedError


class RedisSessionInterface(_PersistentSessionInterface):
    def __init__(self, app=None, timeout=None,
                 redis=None, redis_url=None, prefix=None):
        super(RedisSessionInterface, self).__init__(app, timeout)
        if redis is None:
            assert redis_url or app, \
                'Please provide redis_url or application with REDIS_URL'
            redis_url = redis_url or app.config['REDIS_URL']
            redis = redis_conn.from_settings(redis_url)
        if prefix is None:
            assert app, \
                'Please provide prefix or application with APP_PREFIX'
            prefix = '%s:session:' % app.config['APP_PREFIX']
        self.redis = redis
        self.prefix = prefix

    def _load_data(self, sid):
        data = self.redis.get(self.prefix + sid)
        return data

    def _save_data(self, sid, data, expire):
        self.redis.setex(self.prefix + sid, data, expire)

    def _delete_data(self, sid):
        self.redis.delete(self.prefix + sid)


class MongoSessionInterface(_PersistentSessionInterface):
    cleanup_interval = DEFAULT_MONGO_CLEANUP_INTERVAL

    def __init__(self, app=None, timeout=None,
                 mongodb=None, mongodb_url=None, table=None):
        super(MongoSessionInterface, self).__init__(app, timeout)
        if mongodb is None:
            assert mongodb_url or app, \
                'Please provide mongodb_url or application with MONGODB_URL'
            mongodb_url = mongodb_url or app.config['MONGODB_URL']
            mongodb = mongo_conn.from_settings(mongodb_url)
        if table is None:
            assert app, \
                'Please provide table name or application with APP_PREFIX'
            table = '%s_session' % app.config['APP_PREFIX']
        self.table = mongodb[table]
        self.table.create_index('sid', unique=True, backgroud=True)
        self.table.create_index('expire', background=True)
        self._thread = Thread(target=self._cleanup_thread)
        self._thread.setDaemon(True)
        self._thread.start()

    def _cleanup_thread(self):
        while 1:
            sleep(self.cleanup_interval * uniform(0.7, 1.5))
            self.table.delete_many({'expire': {'$lt': datetime.utcnow()}})

    def _load_data(self, sid):
        record = self.table.find_one(dict(sid=sid))
        if record:
            if record['expire'] > datetime.utcnow():
                return record['data'].encode('iso-8859-1')
            self._delete_data(sid)

    def _save_data(self, sid, data, expiration):
        expire = datetime.utcnow() + timedelta(seconds=expiration)
        record = dict(sid=sid, data=data.decode('iso-8859-1'), expire=expire)
        self.table.update_one(dict(sid=sid), {'$set': record}, upsert=True)

    def _delete_data(self, sid):
        self.table.delete_one(dict(sid=sid))
