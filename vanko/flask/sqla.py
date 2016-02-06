import os
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from ..scrapy.defaults import DEFAULT_PROJECT_DIR
from ..utils import getenv


DEFAULT_PREFIX = 'test'
DEFAULT_ENGINE = ''
DEFAULT_ALLOWED_ENGINES = 'mongodb sqlite'


class _SQLAlchemyMixin(object):

    def __init__(self, *args, **kwargs):
        self._models_registry = {}
        super(_SQLAlchemyMixin, self).__init__(*args, **kwargs)

    def register_models(self, *models, **kwargs):
        add_attributes = kwargs.pop('add_attributes', True)
        assert not kwargs, 'Invalid argument: %s' % ' '.join(kwargs.keys())
        for model_cls in models:
            model_name = model_cls.__name__
            self._models_registry[model_name.lower()] = model_cls
            if add_attributes:
                setattr(self, model_name, model_cls)

    def __getitem__(self, model_name):
        return self._models_registry[model_name.lower()]


class _SQLAlchemyWrapper(_SQLAlchemyMixin):

    Column = sa.Column
    Table = sa.Table
    ForeignKey = sa.ForeignKey
    Integer = sa.Integer
    Float = sa.Float
    Numeric = sa.Numeric
    String = sa.String
    Text = sa.Text
    Unicode = sa.Unicode
    Boolean = sa.Boolean
    Date = sa.Date
    DateTime = sa.DateTime
    Time = sa.Time

    def __init__(self, db_url, echo, *args, **kwargs):
        super(_SQLAlchemyWrapper, self).__init__(*args, **kwargs)
        self._engine = create_engine(db_url, echo=echo)
        self.Model = declarative_base()
        self.Session = sessionmaker(bind=self._engine)
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = self.Session()
        return self._session

    def create_all(self):
        self.Model.metadata.create_all(bind=self._engine)

    def drop_all(self):
        self.Model.metadata.drop_all(bind=self._engine)


def init_db(app=None, app_prefix=DEFAULT_PREFIX, with_registry=True):
    app_prefix = get_app_prefix(app, app_prefix)
    default_db_url = get_default_db_url(app, app_prefix=app_prefix)
    db_url = _get_param(app, 'SQLALCHEMY_DATABASE_URI', default_db_url)

    if app:
        # import it here to avoid extra dependencies in common case
        from flask_sqlalchemy import SQLAlchemy

        if with_registry:
            class SQLAlchemyWithRegistry(_SQLAlchemyMixin, SQLAlchemy):
                pass

            db = SQLAlchemyWithRegistry(app)
        else:
            db = SQLAlchemy(app)
    else:
        db = _SQLAlchemyWrapper(
            db_url, echo=_get_param(app, 'SQLALCHEMY_ECHO', False))
    db.app_prefix = app_prefix

    if db_url.startswith('sqlite:///'):
        db_path = db_url[10:]
        if db_path and db_path != ':memory:':
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir)
                except OSError as e:
                    if 'exists' not in e.strerror:
                        raise
    return db


def _get_param(app, param, default):
    if app:
        return app.config.get(param, default)
    else:
        return getenv(param, default)


def get_db_engine(app=None,
                  allow=DEFAULT_ALLOWED_ENGINES, default=DEFAULT_ENGINE):
    db_engine = _get_param(app, 'DB_ENGINE', default)
    assert db_engine in allow.split(), 'DB_ENGINE must be one of: %s' % allow
    return db_engine


def get_app_prefix(app=None, default=DEFAULT_PREFIX):
    return _get_param(app, 'APP_PREFIX', default)


def get_default_db_url(app=None, engine=None, app_prefix=None,
                       project_dir=DEFAULT_PROJECT_DIR):
    db_engine = engine or get_db_engine(app)
    app_prefix = app_prefix or get_app_prefix(app)
    if db_engine == 'sqlite':
        path = os.path.join(project_dir, app_prefix, 'db.sqlite')
        return 'sqlite:///%s' % path
    if db_engine == 'mongodb':
        return 'mongodb://localhost/%s' % app_prefix
    return ''
