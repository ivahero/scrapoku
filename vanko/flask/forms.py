class _ReadOnlyWidgetProxy(object):
    def __init__(self, widget):
        self.widget = widget

    def __getattr__(self, name):
        return getattr(self.widget, name)

    def __call__(self, field, **kwargs):
        kwargs.setdefault('readonly', True)
        return self.widget(field, **kwargs)


def readonly_field(field):
    def _do_nothing(*args, **kwargs):
        pass

    field.widget = _ReadOnlyWidgetProxy(field.widget)
    field.process = _do_nothing
    field.populate_obj = _do_nothing
    return field
