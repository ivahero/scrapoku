import operator
import logging
from flask import flash
from flask_admin import expose
from flask_admin.model import BaseModelView
from flask_admin.babel import gettext, ngettext, lazy_gettext
from flask_admin.actions import action
from flask_admin.helpers import get_form_data
from flask_admin.model.filters import BaseFilter
from .admin import ModelFieldChoices, ModelViewMixin, ExcelExportViewMixin
from .utils import datacache
from ..utils import JSONEncoder, JSONDecoder

DEFAULT_KEY_FIELD = 'key'


class RedisModelChoices(ModelFieldChoices):
    default_key_field = DEFAULT_KEY_FIELD

    def prepare_kwargs(self, key_field=None, decoder=None, **kwargs):
        self.key_field = key_field or self.default_key_field
        self.decoder = (decoder or JSONDecoder)()
        return kwargs

    def get_default_db(self):
        discovered_storage = {}
        datacache(None, 'discover',
                  _discovered_storage=discovered_storage,
                  **self.datacache_kwargs)
        return discovered_storage.get('redis', None)

    def get_raw_items(self):
        return self.db.hgetall(self.table).iteritems()

    def generate(self):
        if self.table and self.field:
            choices = set()
            decoder = self.decoder
            for key, item in self.get_raw_items():
                item = decoder.decode(item)
                item.setdefault(self.key_field, key)
                value = item.get(self.field)
                if value:
                    choices.add(value)
            return sorted(choices)


class RedisModelFilter(object):
    def __init__(self, dtype, oper):
        self.dtype = dtype
        self.oper = oper

    def __call__(self, column, name=None, options=None):
        return BaseRedisFilter(column, self.dtype, self.oper, name, options)


class BaseRedisFilter(BaseFilter):
    dtype_map = {
        int: dict(name='int', data_type=None, default=0),
        str: dict(name='str', data_type=None, default=''),
        }

    oper_map = {
        '==': dict(text='equals', func=operator.eq),
        '!=': dict(text='not equal', func=operator.ne),
        '>': dict(text='greater', func=operator.gt),
        '<': dict(text='smaller', func=operator.lt),
        }

    def __init__(self, column, dtype, oper, name=None, options=None):
        assert dtype in self.dtype_map
        assert oper in self.oper_map
        self.column = column
        self.dtype = dtype
        self.default = self.dtype_map[dtype]['default']
        self.func = self.oper_map[oper]['func']
        self._operation = self.oper_map[oper]['text']
        name = name or column.title()
        data_type = self.dtype_map[dtype]['data_type']
        super(BaseRedisFilter, self).__init__(name, options, data_type)

    def clean(self, value):
        return self.dtype(value)

    def apply(self, query, value):
        column, dtype, default, func = \
            self.column, self.dtype, self.default, self.func
        value = dtype(value or default)
        return (it for it in query
                if func(dtype(it.get(column, default)), value))

    def operation(self):
        return self._operation


class RedisModelView(
        ModelViewMixin, BaseModelView, ExcelExportViewMixin):
    logger = logging.getLogger('.'.join(__name__.split('.')[-2:]))

    default_key_field = DEFAULT_KEY_FIELD
    case_insensitive_search = False
    item_numbering = False
    export_producer = None

    def __init__(self, name, redis, redis_key=None,
                 key_field=None, encoder=None, decoder=None,
                 *args, **kwargs):
        self.redis = redis
        self.redis_key = redis_key or name.lower().replace(' ', '_')
        self.key_field = key_field or self.default_key_field
        self.encoder = (encoder or JSONEncoder)()
        self.decoder = (decoder or JSONDecoder)()
        name = name or self._prettify_name(self.redis_key)
        endpoint = kwargs.pop('endpoint', name.lower().replace(' ', '-'))
        super(RedisModelView, self).__init__(
            model=None, name=name, endpoint=endpoint, *args, **kwargs)

    def make_pk_for_model(self, model):
        raise NotImplementedError('Please implement make_pk_for_model()')

    def put_one(self, key, model):
        item = self.encode_model(key, model)
        return self.redis.hset(self.redis_key, key, item)

    def get_one(self, pk):
        data = self.redis.hget(self.redis_key, pk)
        return self.decode_model(pk, data)

    def get_raw_list(self):
        redis, redis_key = self.redis, self.redis_key
        # return redis.hgetall(redis_key).iteritems()
        for key in redis.hkeys(redis_key):
            yield key, redis.hget(redis_key, key)

    def delete_many(self, key_list):
        return self.redis.hdel(self.redis_key, *key_list)

    def encode_model(self, key, model):
        if model:
            return self.encoder.encode(model)

    def decode_model(self, key, item):
        if item:
            model = self.decoder.decode(item)
            model.setdefault(self.key_field, key)
            return model

    def init_search(self):
        return bool(self.column_searchable_list)

    def scaffold_sortable_columns(self):
        return []

    def scaffold_pk(self):
        return self.key_field

    def is_valid_filter(self, filter):
        return isinstance(filter, BaseRedisFilter)

    def get_pk_value(self, row):
        return row.get(self.key_field, '')

    def _get_field_value(self, model, name):
        return model.get(name, '')

    def edit_form(self, obj):
        return self._edit_form_class(get_form_data(), **obj)

    def get_pk_for_model(self, model, action):
        # do not trust existing key - model might be edited
        model.pop(self.key_field, None)
        return self.make_pk_for_model(model)

    def update_model(self, form, model):
        try:
            model.update(form.data)
            self._on_model_change(form, model, False)
            old_pk = self.get_pk_value(model)
            new_pk = self.get_pk_for_model(model, 'update')
            self.put_one(new_pk, model)
            if old_pk and old_pk != new_pk:
                self.delete_many([old_pk])
        except Exception, e:
            flash(gettext(
                'Failed to update record. %(error)s', error=str(e)),
                category='error')
            self.logger.exception('Failed to update record.')
            return False
        else:
            self.after_model_change(form, model, False)
        return True

    def create_model(self, form):
        try:
            model = form.data
            self._on_model_change(form, model, True)
            pk = self.get_pk_for_model(model, 'create')
            self.put_one(pk, model)
        except Exception, e:
            flash(gettext(
                'Failed to create record: %(error)s', error=str(e)),
                category='error')
            self.logger.exception('Failed to create record.')
            return False
        else:
            self.after_model_change(form, model, True)
        return model

    def delete_model(self, model):
        try:
            pk = self.get_pk_value(model)
            if not pk:
                raise ValueError('Document does not have _id')
            self.on_model_delete(model)
            self.delete_many([pk])
        except Exception, e:
            flash(gettext('Failed to delete record. %(error)s', error=str(e)),
                  category='error')
            self.logger.exception('Failed to delete record.')
            return False
        else:
            self.after_model_delete(model)
        return True

    def _get_list_and_search(self, search):
        count = -1
        if search and self.case_insensitive_search:
            search = search.lower()
        for key, item in self.get_raw_list():
            count += 1
            model = self.decode_model(key, item)
            if search:
                for col in self.column_searchable_list:
                    value = model.get(col, '')
                    if value:
                        if self.case_insensitive_search:
                            value = value.lower()
                        if search in value:
                            break
                else:
                    continue
            yield model

    def get_list(self, page, sort_field, sort_desc, search, filters,
                 page_size=None):
        data = self._get_list_and_search(search)

        for flt, flt_name, value in filters:
            data = self._filters[flt].apply(data, value)

        sort_field = sort_field or self.column_default_sort
        if sort_field:
            data = list(data)
            data.sort(key=lambda i: i.get(sort_field, None), reverse=sort_desc)

        data = list(data)
        count = len(data)
        start = 0

        if page_size is None:
            page_size = self.page_size
        if int(page_size) > 0:
            start = page * page_size
            data = data[start: start + page_size]

        if self.item_numbering:
            for no, item in enumerate(data, start=start+1):
                item.setdefault('_no', no)

        return count, data

    def is_action_allowed(self, name):
        if name == 'delete' and not self.can_delete:
            return False
        return super(RedisModelView, self).is_action_allowed(name)

    @action('delete',
            lazy_gettext('Delete'),
            lazy_gettext('Are you sure you want to delete selected records?'))
    def action_delete(self, ids):
        try:
            count = self.delete_many(ids)
            flash(ngettext('Record was successfully deleted.',
                           '%(count)s records were successfully deleted.',
                           count,
                           count=count))
        except Exception as ex:
            flash(gettext(
                'Failed to delete records. %(error)s', error=str(ex)),
                category='error')

    @expose('/export/csv/')
    def export_csv(self, *args, **kwargs):
        if self.export_producer is None:
            return super(RedisModelView, self).export_csv(*args, **kwargs)
        return self.export_excel(
            producer=self.export_producer, *args, **kwargs)
