#!/usr/bin/env python2
import re
import sys
import IPython
import ipdb  # noqa
import requests  # noqa

try:
    import scrapy  # noqa
except ImportError, e:
    print 'warning: scrapy import: %s' % e


def start_ipython(fix_argv=True, *args, **kwargs):
    if fix_argv:
        sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    return IPython.start_ipython(*args, **kwargs)


if __name__ == '__main__':
    sys.exit(start_ipython())
