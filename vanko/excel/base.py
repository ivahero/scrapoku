from __future__ import absolute_import
import os
import sys
import errno
import six
import re
import time
import random
import decimal

try:
    from scrapy.exceptions import DropItem
except ImportError:
    DropItem = None

from ..utils import JSONDecoder


class _ItemFieldGetter(object):
    def __init__(self, field):
        self.field = field

    def __call__(self, item):
        return item.get(self.field, '')


class ExcelProducerBase(object):
    exclude_links = True
    default_extension = ''
    default_windows_links = False
    sheet_name_maxlen = 31
    link_maxlen = 255
    write_attempts = 3
    numeric_types = six.integer_types + (float, decimal.Decimal)

    def __init__(self, db=None, table=None, keys=None, settings=None,
                 sort_by=None, filter_by=None, offset=None, limit=None,
                 get_item=None, process_item=None, decoder=None,
                 fields=None, exclude=None, format=None, default_type=None,
                 filepath=None, optimize=None, encoding='utf-8',
                 embed_images=None, image_fields=None, image_path=None,
                 hard_blanks=False, windows_links=None, replace_eol=False,
                 worksheet_key=None, image_shift=None, options=None,
                 show_warnings=None, can_confirm=None, demo_limit=None,
                 title_case=False, key_field=None):

        self.class_name = type(self).__name__
        self.db_type, self.db, self.table, self.key_field = \
            self.detect_db_type(db)
        self.table = table or self.table
        self.key_field = key_field or self.key_field
        self.get_item = get_item
        self.process_item = process_item

        self.settings = settings or self._create_settings()
        self.image_path = self.get_arg(image_path, 'EXCEL_PATH_IMAGES')
        self.optimize = self.get_arg(optimize, 'EXCEL_OPTIMIZE', bool)
        self.embed_images = self.get_arg(embed_images,
                                         'EXCEL_EMBED_IMAGES', bool)
        self.show_warnings = self.get_arg(show_warnings,
                                          'EXCEL_WARNINGS', bool)

        self.filepath = self.get_arg(filepath, 'EXCEL_OUTPUT')
        if not os.path.splitext(self.filepath)[1]:
            self.filepath += self.default_extension

        worksheet_key = self.get_arg(worksheet_key, 'EXCEL_SHEETBY')
        if callable(worksheet_key):
            self.sheet_key_func = worksheet_key
        elif worksheet_key is None or self.strip_decode(worksheet_key) == '':
            self.sheet_key_func = lambda item: ''
        else:
            self.sheet_key_func = _ItemFieldGetter(worksheet_key)

        if windows_links is None:
            windows_links = self.default_windows_links
        self.windows_links = windows_links

        self.image_shift = image_shift
        self.hard_blanks = hard_blanks
        self.replace_eol = replace_eol
        self.encoding = encoding
        self.options = options or {}
        self.title_case = title_case

        if can_confirm is None:
            can_confirm = (os.isatty(sys.stdout.fileno()) and
                           os.isatty(sys.stderr.fileno()))
        self.can_confirm = can_confirm

        self.decoder = decoder or JSONDecoder()
        self.keys = self.data_keys(keys, sort_by, filter_by,
                                   offset, limit, demo_limit)

        self.prepare_format(format, fields, default_type)
        self.prepare_fields(fields, exclude, image_fields)

    @staticmethod
    def detect_db_type(db):
        # Returns: db_type, db, table, key_field
        if db is None:
            return 'none', None, None, None

        try:
            from redis import Redis, StrictRedis
        except ImportError:
            Redis = StrictRedis = None

        if Redis and isinstance(db, (Redis, StrictRedis)):
            return 'redis', db, None, None

        try:
            from pymongo import MongoClient
        except ImportError:
            MongoClient = None

        client = getattr(db, 'client', None)
        if MongoClient and isinstance(client, MongoClient):
            return 'mongo', db, None, 'key'

        try:
            from vanko.scrapy import CustomSpider
        except ImportError:
            CustomSpider = None

        if CustomSpider and isinstance(db, CustomSpider):
            cspider = db
            table = cspider.get_table_name()
            if cspider.backend == 'redis' and cspider.redis:
                return 'redis', cspider.redis, table, None
            if cspider.backend == 'mongo' and cspider.mongo:
                return 'mongo', cspider.mongo, table, cspider.key_field

        raise AssertionError('Unsupported database type')

    @staticmethod
    def _create_settings():
        try:
            from scrapy.settings import Settings
            from vanko.scrapy import CustomSettings
        except ImportError:
            settings = None
        else:
            settings = Settings()
            custom = CustomSettings(base_settings=settings)
            settings.setdict(custom.as_dict(), custom.priority)
        return settings

    def data_keys(self, keys, sort_by, filter_by, offset, limit, demo_limit):
        sort_by = self.get_arg(sort_by, 'EXCEL_SORTBY')
        if isinstance(sort_by, basestring):
            sort_by = _ItemFieldGetter(sort_by)
        assert callable(sort_by) or not sort_by, \
            'sort_by must be string or callable'
        assert callable(filter_by) or not filter_by, \
            'filter_by must be callable'

        offset = max(0, self.get_arg(offset, 'EXCEL_OFFSET', int))
        limit = max(0, self.get_arg(limit, 'EXCEL_LIMIT', int))

        raw_keys = self.raw_data_keys(keys)

        demo_limit = self.get_arg(demo_limit, 'EXCEL_DEMO_LIMIT', int)
        if demo_limit > 0:
            raw_keys = random.sample(raw_keys, min(len(raw_keys), demo_limit))

        if sort_by or filter_by:
            pairs = []
            for key in raw_keys:
                item = self.data_item(key)
                if not filter_by or filter_by(key, item):
                    pairs.append((sort_by(item) if sort_by else key, key))
            keys = [p[1] for p in sorted(pairs)]
        else:
            keys = sorted(raw_keys)

        if offset or limit:
            keys = keys[offset:offset + limit]
        return keys

    def raw_data_keys(self, keys):
        if keys is not None:
            return keys
        keys = self.get_arg(keys, 'EXCEL_KEYS', list)
        if keys:
            return keys
        if self.db_type == 'redis':
            return self.db.hkeys(self.table)
        if self.db_type == 'mongo':
            return self.db[self.table].distinct(self.key_field)
        return []

    def data_item(self, key):
        if self.get_item:
            data = self.get_item(self.db, self.table, key)
            if isinstance(data, dict):
                item = data
            elif (hasattr(data, '__table__') and
                    hasattr(data.__table__, 'columns')):
                item = {c.name: getattr(data, c.name)
                        for c in data.__table__.columns}
            else:
                raise AssertionError('An item must be a dict() or SQL model')
        elif self.db_type == 'redis':
            data = self.db.hget(self.table, key)
            item = self.decoder.decode(data)
        elif self.db_type == 'mongo':
            item = self.db[self.table].find_one({self.key_field: key})
        return item

    def get_arg(self, value, option, type=None):
        if value is not None:
            return value
        if self.settings:
            if type == bool:
                return self.settings.getbool(option)
            elif type == int:
                return self.settings.getint(option)
            elif type == list:
                value = self.settings.get(option)
                if isinstance(value, basestring) and not value.strip():
                    return []
                return self.settings.getlist(option)
            else:
                return self.settings.get(option)

    @staticmethod
    def as_list(val):
        if isinstance(val, basestring):
            return val.strip().split()
        else:
            return val or []

    def strip_decode(self, text):
        try:
            text = six.text_type(text)
        except UnicodeDecodeError:
            text = six.text_type(text.decode(self.encoding, 'replace'))
        return text.strip()

    def prepare_format(self, format, fields, default_type=None):
        self.format = format.copy() if format else {}
        self.link_fields = set()
        self.exclude_fields = set()

        for f in self.as_list(fields):
            ops = self.format.get(f, {})
            if isinstance(ops, dict):
                ops = ops.copy()
            elif ops is None:
                ops = {'exclude': True}
            else:
                ops = {'width': ops}
            width = ops.setdefault('width', 0)
            if width < 0:
                ops['width'] = -width
                ops['align'] = 'wrap'
            ops.setdefault('exclude', False)
            ops.setdefault('type', default_type or 'any')
            ops.setdefault('align', 'left')
            ops.setdefault('link', None)
            if ops['exclude']:
                self.exclude_fields.add(f)
            self.link_fields.add(ops['link'])
            self.format[f] = ops

    def prepare_fields(self, fields, exclude, image_fields):
        self.image_fields = set(self.as_list(image_fields))
        self.exclude_fields.update(self.as_list(exclude or []))
        self.fields = [f for f in self.as_list(fields)
                       if f not in self.exclude_fields and not
                       (self.exclude_links and f in self.link_fields)]

    def get_col_name(self, field):
        fmt = self.format[field]
        def_label = field.title() if self.title_case else field
        return fmt.get('label', fmt.get('col_name', def_label))

    def maybe_blank(self, value):
        if self.hard_blanks:
            if value is None or isinstance(value, basestring) and value == '':
                value = self.blank_value
        return value

    def get_value_link(self, item, field, shorten=False):
        value = item[self.format[field].get('source', field)]
        text = self.strip_decode(value)
        type_ = self.format[field]['type']
        link = valid = None
        via = None

        if self.exclude_links:
            via = self.format[field].get('link')
            if via:
                link = self.strip_decode(item.get(via, ''))
                valid = (type_ == 'any' and (re.match(r'[a-z]+://\S', link) or
                                             re.match(r'mailto:\S@\S$', link)))

        if (not link and type_ == 'any' and isinstance(value, basestring) and
                not (self.embed_images and field in self.image_fields)):
            if re.match(r'https?://', text):
                link = text
                valid = re.match(r'https?://\S+$', link) and '.' in link
                if valid and shorten:
                    value = re.sub(r'^https?://', '', text)
                    if re.match(r'^[^/]+/$', value):
                        value = value[:-1]
            elif re.match(r'file://\S+', text):
                link = re.sub('^file://', '', text)
                valid = True
                if shorten:
                    value = link
                if self.windows_links:
                    link = link.replace('/', '\\')
            elif re.match(r'mailto:', text):
                link = text
                valid = re.match(r'mailto:\S+@\S+', link)
                if valid and shorten:
                    value = re.sub('^mailto:', '', text)
        if not link:
            link = None
        if link and (not valid or len(link) > self.link_maxlen):
            if via:
                value = ('%s (%s)' % (text, link)).strip()
            link = False  # signal caller to force simple string
        return value, link

    def as_number(self, value):
        if isinstance(value, self.numeric_types):
            return value
        text = str(value).strip()
        if text.isdigit():
            return int(text)
        if re.match(r'^\d+[\d,]+\d+(?:\.\d*)?$', text):
            text = text.replace(',', '')
        try:
            return float(text)
        except ValueError:
            return None

    def get_image_path(self, item, field):
        if self.embed_images and not self.optimize \
                and field in self.image_fields:
            value = item[field].strip()
            if value and isinstance(value, basestring) and \
                    not value.startswith(('http://', 'https://')):
                return os.path.join(self.image_path, value)

    def ensure_writable(self, filepath=None, can_confirm=None):
        if filepath is None:
            filepath = self.filepath
        if can_confirm is None:
            can_confirm = self.can_confirm

        directory = os.path.dirname(filepath)
        if not os.path.exists(directory):
            os.makedirs(directory)
        if not os.path.exists(filepath):
            return
        num_attempts = self.write_attempts
        for attempt in xrange(num_attempts):
            try:
                open(filepath, 'a')
            except IOError as err:
                if err.errno == errno.ETXTBSY and attempt < num_attempts - 1:
                    message = 'Please close %s and press enter... ' % filepath
                    if can_confirm:
                        raw_input(message)
                    else:
                        print message
                        time.sleep(10)
                else:
                    raise

    def make_all_data_rows(self, book, keys):
        fields = self.fields
        format = self.format
        self.last_abs_row = 0

        for key in keys:
            item = self.data_item(key)
            for f in self.fields:
                item.setdefault(f, '')
            if self.process_item:
                if DropItem:
                    try:
                        self.process_item(key, item, producer=self)
                    except DropItem:
                        continue
                else:
                    self.process_item(key, item, producer=self)

            shattr = self.get_sheet_attr(book, self.sheet_key_func(item))
            shattr['row'] += 1
            self.last_abs_row += 1

            self.data_row(shattr['row'], item, book, shattr['sheet'],
                          self.last_abs_row, fields, format)

    def get_sheet_attr(self, book, shname):
        shname = '' if shname is None else self.strip_decode(shname)
        shattr = self.sheets.get(self.real_shname.get(shname, shname))
        if shattr is not None:
            return shattr
        real_shname = self.real_shname.get(shname)
        if real_shname is None:
            real_shname = re.sub(r'[\/\\\?\*\[\]]+', '-', shname)
            real_shname = re.sub(r'\s+', ' ', real_shname).strip()
            if len(real_shname) > self.sheet_name_maxlen:
                real_shname = real_shname[:self.sheet_name_maxlen - 3] + '...'
        if real_shname not in self.sheets:
            self.make_new_sheet(book, real_shname, self.fields, self.format)
            if real_shname not in self.sheets:
                if not self.sheets:
                    self.make_new_sheet(book, '', self.fields, self.format)
                real_shname = ''
        self.real_shname[shname] = real_shname
        return self.sheets[real_shname]

    def make_new_sheet(self, book, shname, fields, format):
        sheet = self.create_sheet(book, shname)
        if sheet is not None:
            self.set_dimensions(book, sheet, fields, format)
            self.make_header(book, sheet, fields, format)
            self.sheets[shname] = dict(name=shname, sheet=sheet, row=0)

    def produce(self, can_confirm=None):
        self.blank_value = ' ' if self.hard_blanks else ''
        self.sheets = {}
        self.real_shname = {}

        filepath = self.filepath

        self.ensure_writable(filepath, can_confirm)
        self.book = book = self.create_book(filepath)
        self.make_styles(book)

        self.make_all_data_rows(book, self.keys)

        if not self.sheets:
            self.make_new_sheet(book, '', self.fields, self.format)
        last_col = len(self.fields) - 1
        for shname, shattr in sorted(self.sheets.items()):
            self.close_sheet(book, shattr['sheet'], shattr['row'], last_col)

        self.ensure_writable(filepath, can_confirm)
        self.close_book(book, filepath)
        return filepath

    def create_book(self, filepath):
        raise NotImplementedError(self.class_name)

    def close_book(self, book, filepath):
        raise NotImplementedError(self.class_name)

    def create_sheet(self, book, shname):
        raise NotImplementedError(self.class_name)

    def close_sheet(self, book, sheet, last_row, last_col):
        raise NotImplementedError(self.class_name)

    def make_styles(self, book):
        raise NotImplementedError(self.class_name)

    def set_dimensions(self, book, sheet, fields, format):
        raise NotImplementedError(self.class_name)

    def make_header(self, book, sheet, fields, format):
        raise NotImplementedError(self.class_name)

    def data_row(self, row, item, book, sheet, abs_row, fields, format):
        raise NotImplementedError(self.class_name)
