# -*- coding: utf-8 -*-
from __future__ import absolute_import
import re
from datetime import datetime

try:
    from dateutil.parser import parse as parse_datetime
except ImportError, e:
    parse_datetime = None
    _import_error = e


_date_trans = [
    (ur'янв\S+', 'jan'),
    (ur'фев\S+', 'feb'),
    (ur'мар\S+', 'mar'),
    (ur'апр\S+', 'apr'),
    (ur'ма[йя]', 'may'),
    (ur'июн\S+', 'jun'),
    (ur'июл\S+', 'jul'),
    (ur'авг\S+', 'aug'),
    (ur'сен\S+', 'sep'),
    (ur'окт\S+', 'oct'),
    (ur'ноя\S+', 'nov'),
    (ur'дек\S+', 'dec'),
    (ur'\s+в\s+(\d{1,2}\D)', r' \1'),
    (ur'\s+(\d\d\d\d)\s+г.\s+', r' \1 '),
    (r'(\d{1,2}:\d\d)\s?\D+$', r'\1'),
]


def fix_datetime(text):
    orig = ''
    while orig != text:
        orig = text
        for src, dst in _date_trans:
            text = re.sub(src, dst, text)

    mo = re.match(r'^(\d\d\.\d\d)[.]\s+(\d\d:\d\d)$', text)
    if mo:
        year = datetime.now().year
        text = '{}.{} {}'.format(mo.group(1), year, mo.group(2))

    return text.strip()


def extract_datetime(data, fix=False, dayfirst=False):
    text = data[0] if isinstance(data, (list, tuple)) else data
    text = (text or '').strip().lower()
    if fix:
        text = fix_datetime(text)
    if parse_datetime is None:
        raise _import_error
    if text:
        return parse_datetime(text, dayfirst=dayfirst)
