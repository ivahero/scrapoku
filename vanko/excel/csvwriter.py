from __future__ import absolute_import
from .base import ExcelProducerBase
import csv
import six
import warnings


class CsvProducer(ExcelProducerBase):

    exclude_links = False
    default_extension = '.csv'
    default_windows_links = False

    def __init__(self, *args, **kwargs):
        super(CsvProducer, self).__init__(*args, **kwargs)
        self.hard_blanks = False

    def create_book(self, filepath):
        return open(self.filepath, 'wb')

    def close_book(self, book, filepath):
        book.close()

    def create_sheet(self, book, shname):
        if shname == '':
            return csv.writer(book, dialect='excel')
        if self.show_warnings:
            warnings.warn('csv does not support multiple sheets')

    def close_sheet(self, book, sheet, last_row, last_col):
        pass

    def make_styles(self, book):
        pass

    def set_dimensions(self, book, sheet, fields, format):
        pass

    def make_header(self, book, sheet, fields, format):
        sheet.writerow([six.text_type(self.get_col_name(f))
                        .encode(self.encoding) for f in fields])

    def data_row(self, row, item, book, sheet, abs_row, fields, format):
        data = []
        for f in fields:
            value, link = self.get_value_link(item, f, shorten=False)
            value = six.text_type(link or value)
            if self.replace_eol:
                value = value.replace('\n', self.replace_eol)
            data.append(value.encode(self.encoding))
        sheet.writerow(data)
