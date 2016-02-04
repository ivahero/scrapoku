import re
import sys
from urlparse import urlparse, urljoin
from flask_admin.contrib import pymongo as admin_pymongo
from flask_admin.model import filters as base_filters
from flask_admin.contrib.pymongo import filters as pymongo_filters
from flask_admin.base import expose
from flask import flash, url_for
from flask_admin.babel import gettext, lazy_gettext
from flask_admin.model.base import ViewArgs
from wtforms.form import Form
from wtforms.fields.core import UnboundField
from flask_admin.model.form import wrap_fields_in_fieldlist
from flask_admin.model.fields import ListEditableFieldList

from .utils import datacache
from .admin import ExcelExportViewMixin, ModelViewMixin, ModelFieldChoices


class PyMongoModelChoices(ModelFieldChoices):
    def get_default_db(self):
        discovered_storage = {}
        datacache(None, 'discover',
                  mongodb_table=self.table,
                  _discovered_storage=discovered_storage,
                  **self.datacache_kwargs)
        return discovered_storage.get('mongodb', None)

    def generate(self):
        if self.table and self.field:
            table = self.table
            if isinstance(table, basestring):
                table = self.db[table]
            return sorted(table.distinct(self.field))


def PyMongoModelFilter(base_type, operation):
    type_map = {str: '', unicode: '', bool: 'Boolean'}
    base_type = type_map.get(base_type,
                             getattr(base_type, '__name__', str(base_type)))
    if base_type.islower():
        base_type = base_type.title()

    op_map = {'==': 'Equal', '!=': 'NotEqual', '>': 'Greater', '<': 'Smaller'}
    operation = op_map.get(operation, operation)
    if operation.islower():
        operation = operation.title()

    filter_name = 'PyMongo%s%sFilter' % (base_type, operation)
    this_module = sys.modules[__name__]
    try:
        return getattr(this_module, filter_name)
    except AttributeError:
        pass

    if operation:
        pymongo_filter_name = 'PyMongoFilter%s' % operation
        try:
            PyMongoFilter = getattr(this_module, pymongo_filter_name)
        except AttributeError:
            BasePyMongoFilter = getattr(pymongo_filters, 'Filter' + operation)

            class PyMongoFilter(BasePyMongoFilter):
                def apply(self, query, value):
                    return super(PyMongoFilter, self).apply(query,
                                                            self.clean(value))

            setattr(this_module, pymongo_filter_name, PyMongoFilter)
    else:
        PyMongoFilter = pymongo_filters.BasePyMongoFilter

    if base_type in ('', 'str', 'Str'):
        parent_filters = (PyMongoFilter,)
    else:
        BaseFilter = getattr(base_filters, 'Base%sFilter' % base_type)
        parent_filters = (PyMongoFilter, BaseFilter)

    filter_class = type(filter_name, parent_filters, {})
    setattr(this_module, filter_name, filter_class)
    return filter_class


class PyMongoFilterGreater(pymongo_filters.FilterGreater):
    def apply(self, query, value):
        query.append({self.column: {'$gt': self.clean(value)}})
        return query


class PyMongoFilterSmaller(pymongo_filters.FilterSmaller):
    def apply(self, query, value):
        query.append({self.column: {'$lt': self.clean(value)}})
        return query


class PyMongoFilterRegex(pymongo_filters.BasePyMongoFilter):
    def apply(self, query, value):
        query.append({self.column: {'$regex': value}})
        return query

    def operation(self):
        return lazy_gettext('matches')


class PyMongoDateBetweenFilter(pymongo_filters.BasePyMongoFilter,
                               base_filters.BaseDateBetweenFilter):
    def __init__(self, column, name, options=None, data_type=None):
        super(PyMongoDateBetweenFilter, self).__init__(
            column, name, options, data_type=data_type or 'daterangepicker')

    def apply(self, query, value):
        start, end = self.clean(value)
        query.append({'$and': [{self.column: {'$gte': start}},
                               {self.column: {'$lte': end}}]})
        return query


class PyMongoDateStringEqualFilter(pymongo_filters.FilterEqual,
                                   base_filters.BaseDateFilter):
    def clean(self, value):
        value = super(PyMongoDateStringEqualFilter, self).clean(value)
        return value.strftime('%Y-%m-%d')

    def apply(self, query, value):
        query.append({self.column: self.clean(value)})
        return query


class PyMongoDateStringBetweenFilter(PyMongoDateBetweenFilter):
    def clean(self, value):
        start_end = super(PyMongoDateStringBetweenFilter, self).clean(value)
        return [x.strftime('%Y-%m-%d') for x in start_end]


class PyMongoModelView(
        ModelViewMixin, admin_pymongo.ModelView, ExcelExportViewMixin):
    list_form_class = None
    case_insensitive_search = False
    export_producer = None

    def __init__(self, coll, *args, **kwargs):
        self.coll = coll  # early access to the underlying collection
        super(PyMongoModelView, self).__init__(coll, *args, **kwargs)

    def scaffold_list_form(self, validators):
        editable_fields = self.column_editable_list
        base_form = Form
        template_form = self.list_form_class or self.form
        custom_field_list = ListEditableFieldList
        list_form_class_name = type(self).__name__ + 'ListForm'

        fields = {}
        for name in dir(template_form):
            field = getattr(template_form, name)
            if isinstance(field, UnboundField) and name in editable_fields:
                fields[name] = field

        temp_list_form = type(list_form_class_name, (base_form,), fields)
        field_list_form = wrap_fields_in_fieldlist(
            base_form, temp_list_form, custom_field_list)
        return field_list_form

    class _Obj(object):
        pass

    def update_model(self, form, model):
        try:
            # Rewriting update_model, because ListEditableFieldList
            # produces non-standard form.data, only form.populate_obj()
            # with an intermediate obejct does the trick.
            obj = self._Obj()
            form.populate_obj(obj)
            model.update(obj.__dict__)
            self._on_model_change(form, model, False)
            pk = self.get_pk_value(model)
            self.coll.update(dict(_id=pk), model)
        except Exception as ex:
            flash(gettext('Failed to update record. %(error)s', error=str(ex)),
                  'error')
            admin_pymongo.view.log.exception('Failed to update record.')
            return False
        else:
            self.after_model_change(form, model, False)
        return True

    def _search(self, query, search_term):
        values = filter(None, search_term.split(' '))
        if not (values and self._search_fields):
            return query

        queries = []
        re_opts = re.I if self.case_insensitive_search else 0

        for value in values:
            term = admin_pymongo.tools.parse_like_term(value)
            stmt = [{field: re.compile(term, re_opts)}
                    for field in self._search_fields]
            queries.append(stmt[0] if len(stmt) == 1 else {'$or': stmt})

        queries = queries[0] if len(queries) == 1 else {'$and': queries}
        return {'$and': [query, queries]}

    def get_list_url_with_filter(self, column, value):
        all_filters = self._filters
        flt = [flt for flt in all_filters if flt.column == column]
        arg_tuple = (all_filters.index(flt[0]), flt[0].name, value)
        url = self._get_list_url(ViewArgs(filters=[arg_tuple]))
        index_url = url_for('%s.index_view' % self.endpoint)
        return urljoin(index_url, '?' + urlparse(url).query)

    @expose('/export/csv/')
    def export_csv(self, *args, **kwargs):
        if self.export_producer is None:
            return super(PyMongoModelView, self).export_csv(*args, **kwargs)
        return self.export_excel(
            producer=self.export_producer, *args, **kwargs)
