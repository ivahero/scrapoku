import os
import re

from tempfile import gettempdir
from datetime import datetime
from time import time

from wtforms import form, fields, validators
from werkzeug import secure_filename
from jinja2 import Markup
from flask import request, redirect, current_app
from flask_admin import expose
from flask_admin.helpers import get_redirect_target
from flask_admin._compat import iteritems

from .compat import _json
from .utils import as_choices, datacache, send_file2, DEFAULT_CACHE_TIMEOUT
from ..excel import produce_excel
from ..utils.misc import as_list, delayed_unlink


DEFAULT_FAST_CACHE_TIMEOUT = 5
DEFAULT_UNLINK_DELAY = 2
DEFAULT_TEMP_DIR = os.path.join(gettempdir(), '.flask_admin')


class AppForm(form.Form):
    pass


class LinkFormatter(object):
    def __init__(self, text=None, field=None,
                 rel='nofollow', target='_blank', encoding='utf-8'):
        # flask_admin's csv export wants func.__name__
        self.__name__ = type(self).__name__
        self.text = text
        self.field = field
        self.rel = rel
        self.target = target
        self.encoding = encoding

    def __call__(self, view, context, model, name):
        if isinstance(model, dict):
            value = self.text or model[name]
            link = model.get(self.field or name, '')
        else:
            value = self.text or getattr(model, name)
            link = getattr(model, self.field or name, '')

        try:
            value = unicode(value)
        except UnicodeDecodeError:
            value = value.decode(self.encoding, 'replace')
        value = value.strip()

        if link and re.match(r'https?://', link):
            return Markup('<a href="{}" target="{}" rel="{}">{}</a>'
                          .format(link, self.target, self.rel, value))
        return value


class ModelFieldChoices(object):
    fast_cache_timeout = DEFAULT_FAST_CACHE_TIMEOUT

    def __init__(self, table=None, field=None, db=None, key=None,
                 allow_blank=False, blank_text='-', **kwargs):
        self._db = db
        self.table = table
        self.field = field
        self.allow_blank = allow_blank
        self.blank_text = blank_text
        self.datacache_kwargs = self.prepare_kwargs(**kwargs)
        self.key = key or self.cache_key(db, table, field)
        self.stamp = self.cache = None

    def prepare_kwargs(self, **kwargs):
        return kwargs

    def cache_key(self, db, table, field):
        if table and field:
            table_name = getattr(table, 'name', None)
            if not table_name:
                table_name = getattr(table, '__name__', None)
            if not table_name:
                table_name = str(table)
            return '{}.{}'.format(table_name, field)

    @property
    def db(self):
        if not self._db:
            self._db = self.get_default_db()
        return self._db

    def get_default_db(self):
        raise NotImplementedError

    def generate(self):
        raise NotImplementedError

    def _generate(self):
        def _with_blank(data):
            data = as_list(data)
            if data and not isinstance(data[0], tuple):
                data = as_choices(data)
            return [('', self.blank_text)] + data if self.allow_blank else data
        try:
            return _with_blank(self.generate())
        except StopIteration, e:
            data = e.args[0] if getattr(e, 'args', None) else None
            raise StopIteration(_with_blank(data))

    @property
    def choices(self):
        if self.stamp is None or time() - self.stamp > self.fast_cache_timeout:
            self.cache = datacache(key=self.key, func=self._generate,
                                   **self.datacache_kwargs)
            self.stamp = time()
        return self.cache

    def as_select2(self):
        return [dict(id=choice[0], text=choice[1]) for choice in self.choices]

    def __len__(self):
        return len(self.choices)

    def __getitem__(self, key):
        return self.choices[key]

    def __html__(self):
        # For flask.json.JSONEncoder
        return _json.dumps(self.choices)


class _ActionForm(AppForm):
    pk = fields.HiddenField(validators=[validators.InputRequired()])
    url = fields.HiddenField()


class ModelViewMixin(object):
    def action_form(self):
        return _ActionForm(request.form) if request.form else _ActionForm()

    @expose('/')
    def index_view(self):
        self.clear_caches(periodic=True)
        return super(ModelViewMixin, self).index_view()

    def clear_caches(self, periodic=False):
        if periodic:
            last = getattr(self, 'datacache_cleared', None)
            if not last:
                self.datacache_cleared = time()
                return
            datacache_timeout = getattr(
                self, 'datacache_timeout', current_app.config.get(
                    'DATACACHE_TIMEOUT', DEFAULT_CACHE_TIMEOUT))
            if time() - last < datacache_timeout:
                return
        self._refresh_filters_cache()
        self.datacache_cleared = time()

    def redirect_back(self, endpoint='.index_view', param_name='url'):
        return redirect(get_redirect_target(param_name) or
                        self.get_url(endpoint))


class ExcelExportViewMixin(object):
    def export_excel(self, producer=None, tempdir=None, *args, **kwargs):
        # Macros in column_formatters are not supported.
        # Macros will have a function name 'inner'
        # This causes non-macro functions named 'inner' not work.
        for col, func in iteritems(self.column_formatters):
            if getattr(func, '__name__', '') == 'inner':
                raise NotImplementedError(
                    'Macros not implemented. Override with '
                    'column_formatters_export. Column: %s' % (col,)
                )

        # Grab parameters from URL
        view_args = self._get_list_extra_args()

        # Map column index to column name
        sort_column = self._get_column_by_idx(view_args.sort)
        sort_column = None if sort_column is None else sort_column[0]

        count, data = self.get_list(0, sort_column, view_args.sort_desc,
                                    view_args.search, view_args.filters,
                                    page_size=self.export_max_rows)

        tempdir = tempdir or DEFAULT_TEMP_DIR
        filename = '%s_%s' % (self.name,
                              datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        filepath = os.path.join(tempdir, filename)

        filepath = produce_excel(
            keys=list(range(count)), get_item=lambda db, table, key: data[key],
            producer=producer, filepath=filepath, title_case=True,
            fields=[col[0] for col in self._export_columns],
            format=getattr(self, 'column_format_excel', None))

        unlink_delay = getattr(self, 'unlink_delay', DEFAULT_UNLINK_DELAY)
        delayed_unlink(filepath, unlink_delay)
        return send_file2(
            filepath, as_attachment=True,
            attachment_filename=secure_filename(os.path.basename(filepath)))
