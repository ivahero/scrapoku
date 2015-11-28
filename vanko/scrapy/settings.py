import os
import re
from scrapy.settings import Settings, SETTINGS_PRIORITIES, default_settings
from .defaults import ACTION_PARAMETER, DEFAULT_ACTION, CUSTOM_SETTINGS
from .helpers import spider_data_dir
from ..utils.misc import infer_type


class CustomSettings(object):
    _max_recursion = 3
    _attr_regex = r'^(%s)_(any|str|tmpl|int|float|bool|dict|list)' \
                  r'(?:_map_([a-z]+))?(?:_on_([a-z]+))?$'
    _priority = {}

    @classmethod
    def register(cls, **kwargs):
        assert kwargs
        for name, default in sorted(kwargs.items()):
            type = None
            mo = re.match('^(.*)_(tmpl.*)$', name)
            if mo:
                name, type = mo.group(1, 2)
            cls.register_param(name, default, type)

    @classmethod
    def register_param(cls, name, default=None, type=None, _priority=True):
        default, type = infer_type(default, type)
        if type == str and '%(spider)s' in (default or ''):
            type = 'tmpl'
        type_str = getattr(type, '__name__', str(type))
        attr = '%s_%s' % (name, type_str)
        val = default
        if type is dict:
            val = getattr(cls, attr, {})
            val.update(default)
        setattr(cls, attr, val)
        cls._priority[attr] = _priority

    @classmethod
    def register_map(cls, name, mapping=None, **kwargs):
        assert name and isinstance(name, str), 'Invalid map name'
        if mapping:
            assert isinstance(mapping, dict) and not kwargs, \
                'Only a dict or key-value pairs are accepted'
        else:
            mapping = kwargs
        setattr(cls, '%s_map' % name, mapping)

    @classmethod
    def register_object(cls, obj, _priority=True):
        attr_list = sorted(dir(cls))
        for name, val in sorted(obj.__dict__.items()):
            if not name.isupper() or val is None or isinstance(val, dict):
                continue
            if _priority or all(not re.match(cls._attr_regex % name, attr)
                                for attr in attr_list):
                cls.register_param(name, val, _priority=_priority)

    def as_dict(self):
        return self.result_dict

    def __init__(self, spider_name='spider', base_settings=None,
                 priority='project'):
        self.attr_list = sorted(dir(self))
        self.base_settings = (base_settings or Settings()).copy()
        self.action = self.base_settings.get(ACTION_PARAMETER, DEFAULT_ACTION)
        if isinstance(priority, basestring):
            priority = SETTINGS_PRIORITIES[priority]
        self.priority = priority
        self.result_dict = {}
        self.in_first_pass = {}
        self.template_keys = _LazyTemplateKeys(spider_name)
        self._process_all_attrs()

    def _process_all_attrs(self):
        for attr_name in self.attr_list:
            self._process_attr(attr_name, 0)
        for loop in xrange(self._max_recursion):
            need_next = False
            for attr_name in self.attr_list:
                try:
                    self._process_attr(attr_name, loop+1)
                except KeyError:
                    if loop == self._max_recursion - 1:
                        raise
                    bad_attr = attr_name
                    need_next = True
            if not need_next:
                return
        raise AssertionError('Template loop on setting %s' % bad_attr)

    def _process_attr(self, attr_name, loop):
        if not hasattr(self, attr_name):
            return
        mo = re.match(self._attr_regex % '[A-Z_]+?', attr_name)
        if not mo:
            return
        opt, opt_type, map_name, on_action = mo.groups()

        first_pass = loop == 0
        is_template_key = opt_type in ('str', 'int', 'bool')

        if first_pass != is_template_key:
            return
        if first_pass and on_action:
            return
        if on_action and on_action not in self.action.split(','):
            return
        if self.result_dict.get(opt, None) and self.in_first_pass[opt]:
            return

        if opt_type == 'dict':
            val = getattr(self, attr_name).copy()
            val.update(self.base_settings.getdict(opt))
        else:
            val = self._get_scalar_val(opt, opt_type, attr_name, map_name)

        self.result_dict[opt] = self.template_keys[opt] = val
        self.in_first_pass[opt] = \
            first_pass and self._priority.get(attr_name, True)
        return True

    def _get_scalar_val(self, opt, opt_type, attr_name, map_name):
        base = self.base_settings.attributes
        if opt in base and base[opt].priority >= self.priority:
            val = base[opt].value
        else:
            val = os.environ.get(opt, getattr(self, attr_name))

        try:
            if opt_type == 'str':
                val = str(val)
            elif opt_type == 'tmpl':
                val = self._expand_template_val(opt, val)
            elif opt_type == 'int':
                val = int(val)
            elif opt_type == 'bool':
                val = bool(int(val))
            elif opt_type == 'list':
                if not isinstance(val, list):
                    val = (val or '').strip()
                    val = [x.strip() for x in val.split(',')] if val else []
        except ValueError as err:
            raise ValueError('cannot convert option %s ("%s"): %s' %
                             (opt, val, err))

        if map_name:
            val_map = getattr(self, map_name + '_map')
            if val in val_map:
                val = val_map[val]
                if opt_type == 'tmpl':
                    val = self._expand_template_val(opt, val)
            elif re.match(r'^[a-z0-9_-]+$', val):
                raise KeyError(
                    'mapping "%s" from option %s not found in: %s' %
                    (val, opt, ', '.join(sorted(val_map))))

        return val

    def _expand_template_val(self, opt, val, only_whole=False):
        loop = 0
        while re.search(r'%[\(\[\{][\w\d_]+[\)\]\}]\w', val):
            val = re.sub(r'%{([\w_][\w\d_]*)}', r'%(\1)', str(val))
            val = re.sub(r'%\[([\w_][\w\d_]*)\]', r'%(\1)', val)
            try:
                val = val % self.template_keys
            except KeyError as err:
                all_keys = sorted(map(str, self.template_keys.keys()))
                raise KeyError('formatter "{}" from option {} '
                               'not found in: {}'.format(
                                   err.args[0], opt, ', '.join(all_keys)))
            loop += 1
            assert loop < self._max_recursion, \
                'Maximum recursion level reached'
        return val


class _LazyTemplateKeys(object):
    lazy_keys = {
        'project_dir': lambda spider: spider_data_dir(),
        'spider_dir': lambda spider: spider_data_dir(spider),
        'files_dir': lambda spider: spider_data_dir(spider, 'files'),
        'images_dir': lambda spider: spider_data_dir(spider, 'images'),
        'mirror_dir': lambda spider: spider_data_dir(spider, 'mirror'),
    }

    def __init__(self, spider_name):
        self.spider = spider_name
        self.cache = {'spider': self.spider}

    def __getitem__(self, key):
        return (key in self.cache and self.cache[key] or
                self.cache.setdefault(key, self.lazy_keys[key](self.spider)))

    def __setitem__(self, key, val):
        self.cache[key] = val

    def keys(self):
        return self.cache.keys()


CustomSettings.register(**CUSTOM_SETTINGS)
CustomSettings.register_object(default_settings, _priority=False)
