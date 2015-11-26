import os
import sys
from scrapy.utils import project as _proj_utils
from scrapy.settings import Settings
from scrapy.crawler import CrawlerProcess
from scrapy.exceptions import NotConfigured

from .defaults import (DEFAULT_BOT_NAME, DEFAULT_SCRAPY_DIR, DEFAULT_LOG_DIR,
                       ACTION_ARGUMENT, PARAM_ARGUMENT, INITIAL_CWD)
from .spider_loader import CustomSpiderLoader


def _patch__project_data_dir():
    _orig_project_data_dir = _proj_utils.project_data_dir

    def new_project_data_dir(project='default'):
        env_dir = os.environ.get('SCRAPY_DATA_DIR', None)
        if env_dir:
            return env_dir
        try:
            return _orig_project_data_dir(project)
        except OSError as e:
            if 'exists' not in e.strerror:
                raise
            # directory exists, try again
            return _orig_project_data_dir(project)
        except NotConfigured:
            return DEFAULT_SCRAPY_DIR

    _proj_utils.project_data_dir = new_project_data_dir

_patch__project_data_dir()


def run_spider(spider_cls, action=None, argv=None, env=None,
               project=None, data_dir=None, module=None):
    if module is None:
        module = spider_cls.__module__
    if isinstance(module, basestring):
        module_name = module
    else:
        module_name = module.__name__

    bot_name = setup_spider(module_name)
    os.environ.setdefault('SCRAPY_PROJECT', project or bot_name)
    os.environ.setdefault('SCRAPY_SETTINGS_MODULE', module_name)
    os.environ.setdefault('SCRAPY_DATA_DIR', data_dir or DEFAULT_SCRAPY_DIR)

    params = {}
    if argv:
        for val in sys.argv[1:]:
            if val.startswith(ACTION_ARGUMENT):
                action = val[len(ACTION_ARGUMENT):]
                if isinstance(argv, (list, tuple)) and action not in argv:
                    action = argv[0]
            elif val.startswith(PARAM_ARGUMENT):
                name, _, value = val[len(PARAM_ARGUMENT):].partition('=')
                params[name] = value
    os.environ.update(params)

    if env:
        assert isinstance(env, dict)
        for key, val in env.items():
            os.environ[str(key)] = str(val)

    settings = Settings()
    settings.setmodule(module_name)

    if action:
        settings.set('ACTION', action)

    cprocess = CrawlerProcess(settings)
    cprocess.crawl(spider_cls)
    cprocess.start()
    return 0


def setup_spider(module, project=None, data_dir=None, spider_modules=None,
                 bot_name=None, module_path=None, spider_loader=None,
                 fix_module=True, fix_env=True, fix_sys_path=False):
    if isinstance(module, basestring):
        module_name = module
        module = sys.modules[module_name]
    else:
        module_name = module.__name__

    if not module_path:
        module_path = getattr(module, '__file__', None)
    if not module_path:
        if module_name == '__main__' and sys.argv[0] not in ('', '-c'):
            module_path = sys.argv[0]

    if module_path and not os.path.isabs(module_path):
        module_path = os.path.abspath(os.path.join(INITIAL_CWD, module_path))

    frozen = getattr(sys, 'frozen', None)
    module_dir = os.path.dirname('' if frozen else module_path)
    package = getattr(module, '__package__', None)

    if not bot_name:
        bot_name = getattr(module, 'BOT_NAME',
                           os.environ.get('BOT_NAME', None))
        if not bot_name:
            bot_name = module_name.rpartition('.')[2]
            if bot_name in '__main__ __parents_main__'.split():
                file_name = os.path.basename(module_path or '')
                bot_name = os.path.splitext(file_name)[0]
            if bot_name in '__init__ __main__ main spider gui web'.split():
                bot_name = os.path.basename(module_dir)
            bot_name = bot_name or (package or '').rpartition('.')[2]
            bot_name = bot_name or DEFAULT_BOT_NAME

    if not spider_modules:
        spider_modules = getattr(module, 'SPIDER_MODULES', module_name)

    if not spider_loader:
        spider_loader = '{}.{}'.format(CustomSpiderLoader.__module__,
                                       CustomSpiderLoader.__name__)
        spider_loader = getattr(module, 'SPIDER_LOADER_CLASS', spider_loader)

    if fix_module:
        setattr(module, 'BOT_NAME', bot_name)
        setattr(module, 'SPIDER_MODULES', spider_modules)
        setattr(module, 'SPIDER_LOADER_CLASS', spider_loader)

    if not project:
        project = getattr(module, 'SCRAPY_PROJECT',
                          os.environ.get('SCRAPY_PROJECT', project))
        project = (project is None) and bot_name or (project or 'default')

    if fix_env:
        os.environ['SCRAPY_PROJECT'] = project
        os.environ['SCRAPY_SETTINGS_MODULE'] = module_name

    if not data_dir:
        data_dir = getattr(module, 'SCRAPY_DATA_DIR',
                           os.environ.get('SCRAPY_DATA_DIR', None))
    if not data_dir:
        try:
            data_dir = _proj_utils.project_data_dir(project)
        except NotConfigured:
            pass

    if data_dir:
        data_dir = os.path.expanduser(data_dir)
        if not os.path.isabs(data_dir):
            data_dir = os.path.abspath(os.path.join(INITIAL_CWD, data_dir))

    if fix_env and data_dir:
            os.environ['SCRAPY_DATA_DIR'] = data_dir

    root_dir = os.path.dirname(module_dir)
    if fix_sys_path and root_dir and (root_dir not in sys.path):
        sys.path.append(root_dir)

    return bot_name


def spider_data_dir(spider=None, subdir=None, project=None):
    project = project or os.environ.get('SCRAPY_PROJECT', 'default')
    path = _proj_utils.project_data_dir(project)

    if spider is None:
        spider_name = None
    elif isinstance(spider, basestring):
        spider_name = spider
    else:
        spider_name = getattr(spider, 'name', DEFAULT_BOT_NAME)

    if spider_name:
        path = os.path.join(path, spider_name)
    if subdir:
        path = os.path.join(path, subdir)

    if not os.path.exists(path):
        os.makedirs(path)

    return path


class _UnbufferedStreamWrapper(object):
    __setstate__ = None

    def __init__(self, stream):
        self._stream = stream

    def write(self, data):
        self._stream.write(data)
        self._stream.flush()

    def __getattr__(self, attr):
        return getattr(self._stream, attr)


def setup_stderr(module_name, silent=None, autoflush=True,
                 log_name=None, log_dir=None, pid_in_name=False, append=False):
    if silent is None:
        silent = (sys.platform == 'win32')
    debugging = bool(int(os.environ.get('DEBUG', False)))
    try:
        __IPYTHON__
    except NameError:
        pass
    else:
        debugging = True
    if debugging:
        return

    project_name = setup_spider(module_name)
    if not log_name:
        if pid_in_name:
            log_name = '{0}.{1}.log'.format(project_name, os.getpid())
        else:
            log_name = '{0}.log'.format(project_name)
    log_path = log_name
    if not os.path.isabs(log_path):
        log_path = os.path.join(log_dir or DEFAULT_LOG_DIR, log_path)
    log_dir = os.path.dirname(log_path)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = open(log_path, mode=('a' if append else 'w'), buffering=1)
    if not silent:
        print 'See {} log at {}'.format(project_name, log_path)

    sys.stdout.flush()
    sys.stderr.flush()
    try:
        sys.stdout.fileno()
        sys.stderr.fileno()
    except AttributeError:
        log_file.write('Redirect stdout (platform: {}, frozen: {})\n'.format(
            sys.platform, getattr(sys, 'frozen', False)))
        sys.stdout = sys.stderr = log_file
    else:
        os.dup2(log_file.fileno(), sys.stderr.fileno())
        os.dup2(log_file.fileno(), sys.stdout.fileno())
    if autoflush:
        sys.stdout = _UnbufferedStreamWrapper(sys.stdout)

    return log_path
