import six
from scrapy import Item, Field
from scrapy.loader import ItemLoader
from scrapy.loader.processors import TakeFirst, MapCompose, Join, Identity

from ..utils import extract_datetime


def SimpleItem(names, base_class=Item):
    """Creates an Item class with given fields specification.
    Usage::
        BaseItem = NewItem('title body url')
        QuestionItem = NewItem('tags status', base_cls=BaseItem)
        AnswerItem = NewItem('user', base_cls=BaseItem)
    """
    if isinstance(names, basestring):
        names = names.split()
    attrs = dict((name, Field()) for name in names)
    class_name = '%s[%s]' % (base_class.__name__, ' '.join(names))
    return type(class_name, (base_class,), attrs)


class TakeFirstItemLoader(ItemLoader):
    default_output_processor = TakeFirst()


TFItemLoader = TakeFirstItemLoader


class IdentityField(Field):
    def __init__(self, *args, **kwargs):
        super(IdentityField, self).__init__(
            input_processor=Identity(), *args, **kwargs)


class StripField(Field):
    def __init__(self, *args, **kwargs):
        super(StripField, self).__init__(
            input_processor=MapCompose(six.text_type.strip), *args, **kwargs)


class JoinField(Field):
    def __init__(self, sep=None, strip=False, *args, **kwargs):
        kw = kwargs.copy()
        if strip:
            kw['input_processor'] = MapCompose(six.text_type.strip)
        if sep is not None:
            kw['output_processor'] = Join(sep)
        super(JoinField, self).__init__(*args, **kw)


class DateTimeField(Field):
    def __init__(self, fix=False, dayfirst=False, *args, **kwargs):
        self.fix = fix
        self.dayfirst = dayfirst
        super(DateTimeField, self).__init__(
            output_processor=self.extract_datetime, *args, **kwargs)

    def extract_datetime(self, data):
        return extract_datetime(
            data, fix=self.fix, dayfirst=self.dayfirst)
