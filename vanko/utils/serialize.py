import json
import datetime
import decimal

try:
    from twisted.internet import defer
except ImportError:
    defer = None

try:
    from scrapy.http import Request, Response
    from scrapy.item import BaseItem
except ImportError:
    Request = Response = BaseItem = None


class JSONEncoder(json.JSONEncoder):
    DATE_FORMAT = '%Y-%m-%d'
    TIME_FORMAT = '%H:%M:%S'

    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.strftime("%s %s" % (self.DATE_FORMAT, self.TIME_FORMAT))
        elif isinstance(o, datetime.date):
            return o.strftime(self.DATE_FORMAT)
        elif isinstance(o, datetime.time):
            return o.strftime(self.TIME_FORMAT)
        elif isinstance(o, decimal.Decimal):
            return str(o)
        elif defer and isinstance(o, defer.Deferred):
            return str(o)
        elif BaseItem and isinstance(o, BaseItem):
            return dict(o)
        elif Request and isinstance(o, Request):
            return "<%s %s %s>" % (type(o).__name__, o.method, o.url)
        elif Response and isinstance(o, Response):
            return "<%s %s %s>" % (type(o).__name__, o.status, o.url)
        else:
            return super(JSONEncoder, self).default(o)


class JSONDecoder(json.JSONDecoder):
    pass
