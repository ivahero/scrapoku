import os
import sys
import subprocess
import time
import random
import threading
import socket


class classproperty(object):
    def __init__(self, fget):
        self.fget = fget

    def __get__(self, owner_self, owner_cls):
        return self.fget(owner_cls)


def infer_type(default, type):
    if type is None:
        for type in (bool, int, float, list, dict):
            if isinstance(default, type):
                break
        else:
            type = str
    if default is None:
        default = type()
    return default, type


def cast_type(value, default, type=None):
    default, type = infer_type(default, type)
    if type == bool:
        value = int(value)
    return type(value)


def getenv(name, default=None, type=None):
    default, type = infer_type(default, type)
    value = os.environ.get(name, default)
    return cast_type(value, default, type)


def launch_file(path):
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'linux2':
        subprocess.call(['xdg-open', path])
    elif sys.platform == 'darwin':
        subprocess.call(['open', path])
    else:
        raise AssertionError('Unsupported platform: %s' % sys.platform)


def as_list(result):
    if result is None:
        return []
    elif isinstance(result, (list, tuple)):
        return list(result)
    elif hasattr(result, 'next') and callable(result.next):
        return list(result)
    else:
        return [result]


def cut_str(text, length):
    text = text or ''
    if len(text) > length:
        text = text[:length] + '...'
    return text


def randsleep(delay, min_factor=0.5, max_factor=1.5):
    delay *= random.uniform(min_factor, max_factor)
    time.sleep(delay)
    return delay


def safe_unlink(path):
    try:
        os.unlink(path)
    except Exception:
        pass


def delayed_unlink(path, delay=0):
    def _unlink_thread(path, delay):
        if delay > 0:
            time.sleep(delay)
        safe_unlink(path)
    if delay > 0:
        threading.Thread(target=_unlink_thread, args=(path, delay)).start()
    else:
        safe_unlink(path)


def getrunid():
    return '{}:{}:{}'.format(os.environ.get('APP_NAME', '-'),
                             os.environ.get('DYNO', socket.gethostname()),
                             os.getpid())


def get_func_name(func):
    try:
        func = func.im_func
    except AttributeError:
        pass
    try:
        return func.__name__
    except AttributeError:
        return str(func)
