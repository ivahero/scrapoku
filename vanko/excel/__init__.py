from __future__ import absolute_import
import os
from .csvwriter import CsvProducer


try:
    from ..scrapy import CustomSettings, DEFAULT_PROJECT_DIR
except ImportError:
    pass
else:
    DEFAULT_EXCEL_DIR = os.path.join(DEFAULT_PROJECT_DIR, 'excel')

    CustomSettings.register(
        EXCEL_PRODUCER='xlsx',  # choices: xlsx, csv, openpyxl
        EXCEL_OPTIMIZE=False,
        EXCEL_WARNINGS=False,
        EXCEL_EMBED_IMAGES=False,
        EXCEL_KEYS='',
        EXCEL_OFFSET=0,
        EXCEL_LIMIT=0,
        EXCEL_DEMO_LIMIT=0,
        EXCEL_SORTBY='',
        EXCEL_SHEETBY='',
        EXCEL_PATH_IMAGES=os.path.join(DEFAULT_EXCEL_DIR,
                                       '%(spider)s', 'images'),
        EXCEL_OUTPUT=os.path.join(DEFAULT_EXCEL_DIR,
                                  '%(spider)s', '%(spider)s'),
        )


PRODUCER_MAP = {}

PRODUCER_MAP['csv'] = CsvProducer

try:
    import xlsxwriter
    del xlsxwriter
except ImportError:
    pass
else:
    from .xlsxwriter import XlsxProducer
    PRODUCER_MAP['xlsx'] = XlsxProducer

try:
    import openpyxl
    del openpyxl
except ImportError:
    pass
else:
    from .openpyxl import OpenpyxlProducer
    PRODUCER_MAP['pyxl'] = OpenpyxlProducer


def produce_excel(producer=None, settings=None, *args, **kwargs):
    producer = PRODUCER_MAP.get(producer or settings.get('EXCEL_PRODUCER'))
    if producer is None:
        raise NotImplementedError(producer)
    return producer(*args, settings=settings, **kwargs).produce()
