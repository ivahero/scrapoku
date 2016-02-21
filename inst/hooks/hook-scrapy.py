from PyInstaller.utils.hooks import get_package_paths
from os.path import join, dirname, exists, sep

_, scrapy_pkg_dir = get_package_paths('scrapy')

hiddenimports = []
base_dir = dirname(scrapy_pkg_dir)
py_module = 'scrapy.settings.default_settings'
py_path = join(base_dir, py_module.replace('.', sep) + '.py')
py_vars = {'__file__': py_path}
execfile(py_path, py_vars)


def maybe_add(name, item):
    if item and item not in hiddenimports:
        for module in item, item + '.__init__':
            path = join(base_dir, module.replace('.', sep))
            if exists(path + '.py') or exists(path + '.pyc'):
                hiddenimports.append(item)
                return True

for name, value in sorted(py_vars.items()):
    if not name.isupper():
        continue
    if isinstance(value, dict):
        seq = sorted(value.keys() + value.values())
    elif isinstance(value, basestring):
        seq = [value]
    elif isinstance(value, (list, tuple)):
        seq = value
    else:
        continue
    for item in seq:
        if isinstance(item, basestring) and item.startswith('scrapy.'):
            maybe_add(name, item) or maybe_add(name, item.rpartition('.')[0])

hiddenimports += [
    'scrapy.pipelines.images',
]

datas = [
    (join(scrapy_pkg_dir, 'VERSION'), 'scrapy'),
    (join(scrapy_pkg_dir, 'mime.types'), 'scrapy'),
]
