import six
import types
from scrapy import Spider
from scrapy.utils import reqser

_request_to_dict_handlers = []
_request_from_dict_handlers = []


def _patch_reqser():
    global _orig_request_to_dict, _orig_request_from_dict
    _orig_request_to_dict = reqser.request_to_dict
    _orig_request_from_dict = reqser.request_from_dict
    reqser.request_to_dict = request_to_dict2
    reqser.request_from_dict = request_from_dict2


def add_reqser_handlers(to_dict_func, from_dict_func):
    if to_dict_func and to_dict_func not in _request_to_dict_handlers:
        _request_to_dict_handlers.append(to_dict_func)
    if from_dict_func and from_dict_func not in _request_from_dict_handlers:
        _request_from_dict_handlers.insert(0, from_dict_func)


def request_to_dict2(request, spider=None):
    d = _orig_request_to_dict(request, spider)
    for handler in _request_to_dict_handlers:
        d = handler(d, request, spider)
    return d


def request_from_dict2(d, spider=None):
    request = _orig_request_from_dict(d, spider)
    for handler in _request_from_dict_handlers:
        request = handler(d, request, spider)
    return request


def request_is_serializable(request):
    for callback in request.callback, request.errback:
        if callback is None or isinstance(callback, basestring):
            continue
        if isinstance(callback, types.MethodType):
            obj = six.get_method_self(callback)
            if not isinstance(obj, Spider):
                return False
            func = six.get_method_function(callback)
            attr = getattr(obj, func.__name__, None)
            if callable(attr):
                continue
        if isinstance(callback, types.FunctionType) and \
                callback.__name__.isalnum():
            continue
        return False
    return True


_patch_reqser()
