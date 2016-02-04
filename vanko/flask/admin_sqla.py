import sys
from flask_admin.contrib import sqla as admin_sqla
from flask_admin.contrib.sqla import filters as sqla_filters
from flask_admin.base import expose

from .admin import ModelViewMixin, ExcelExportViewMixin


def SQLAModelFilter(base_type, operation):
    type_map = {str: '', unicode: '', bool: 'Boolean'}
    base_type = type_map.get(base_type,
                             getattr(base_type, '__name__', str(base_type)))
    if base_type.islower():
        base_type = base_type.title()

    op_map = {'==': 'Equal', '!=': 'NotEqual', '>': 'Greater', '<': 'Smaller'}
    operation = op_map.get(operation, operation)
    if operation.islower():
        operation = operation.title()

    this_module = sys.modules[__name__]
    if base_type:
        filter_name = '%s%sFilter' % (base_type, operation)
        try:
            return getattr(this_module, 'SQLA' + filter_name)
        except AttributeError:
            return getattr(sqla_filters, filter_name)
    else:
        return getattr(sqla_filters, 'Filter%s' % operation)


class SQLADateStringEqualFilter(sqla_filters.DateEqualFilter):
    def apply(self, query, value, alias=None):
        value = value.strftime('%Y-%m-%d')
        return query.filter(self.get_column(alias) == value)


class SQLADateStringBetweenFilter(sqla_filters.DateBetweenFilter):
    def apply(self, query, value, alias=None):
        start, end = [date.strftime('%Y-%m-%d') for date in value]
        return query.filter(self.get_column(alias).between(start, end))


class SQLAModelView(
        ModelViewMixin, admin_sqla.ModelView, ExcelExportViewMixin):
    export_producer = None

    @expose('/export/csv/')
    def export_csv(self, *args, **kwargs):
        if self.export_producer is None:
            return super(SQLAModelView, self).export_csv(*args, **kwargs)
        return self.export_excel(
            producer=self.export_producer, *args, **kwargs)

    def get_filters(self):
        for flt in self.column_filters or ():
            if isinstance(getattr(flt, 'column', None), str):
                flt.column = getattr(self.model, flt.column)
        return super(SQLAModelView, self).get_filters()
