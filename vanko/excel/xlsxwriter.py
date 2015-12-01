from __future__ import absolute_import
from .base import ExcelProducerBase
from xlsxwriter import Workbook


class XlsxProducer(ExcelProducerBase):

    width_factor = 1.0
    default_extension = '.xlsx'
    default_windows_links = True

    def __init__(self, *args, **kwargs):
        super(XlsxProducer, self).__init__(*args, **kwargs)

    def create_book(self, filepath):
        return Workbook(filepath, {'constant_memory': self.optimize})

    def close_book(self, book, filepath):
        book.close()

    def create_sheet(self, book, shname):
        if shname:
            return book.add_worksheet(shname)
        else:
            return book.add_worksheet()

    def close_sheet(self, book, sheet, last_row, last_col):
        sheet.freeze_panes(1, min(last_col, 1))
        if last_row > 0 and last_col >= 0:
            sheet.autofilter(0, 0, last_row, last_col)
        if last_row > 1 and last_col > 1:
            sheet.hide_gridlines(option=2)  # on screen and printed

    def set_dimensions(self, book, sheet, fields, format):
        for c, f in enumerate(fields):
            w = format[f].get('width')
            if w:
                sheet.set_column(c, c, w * self.width_factor)

    def make_styles(self, book):
        self.fmt_head = book.add_format(dict(
            bold=1, align='center', left=1, right=1, top=2, bottom=2))
        self.fmt_left = book.add_format(dict(
            align='left', border=1, valign='top'))
        self.fmt_center = book.add_format(dict(
            align='center', border=1, valign='top'))
        self.fmt_wrap = book.add_format(dict(
            align='left', text_wrap=1, border=1, valign='top'))
        self.fmt_currency = book.add_format(dict(
            align='left', border=1, valign='top', num_format='#,##0.00'))
        link1 = dict(font_color='blue', underline=1, border=1, valign='top')
        self.fmt_link = book.add_format(link1)
        link2 = link1.copy()
        link2['align'] = 'center'
        self.fmt_link_center = book.add_format(link2)
        link3 = link1.copy()
        link3['text_wrap'] = 1
        self.fmt_link_wrap = book.add_format(link3)

    def make_header(self, book, sheet, fields, format):
        for col, f in enumerate(fields):
            sheet.write_string(0, col, self.get_col_name(f), self.fmt_head)

    def data_row(self, row, item, book, sheet,
                 abs_row, fields, format):
        img_no = 1
        shorten_links = self.options.get('shorten_links', False)
        for col, f in enumerate(fields):
            align = format[f]['align']
            type_ = format[f]['type']
            value, link = self.get_value_link(item, f, shorten=shorten_links)
            text = self.strip_decode(value)
            img_path = self.get_image_path(item, f)

            if img_path:
                if self.image_shift is None:
                    img_col = len(fields) + img_no
                else:
                    img_col = col + self.image_shift
                sheet.insert_image(row, img_col, img_path)
                img_no += 1

            if align == 'wrap':
                fmt_cell = self.fmt_wrap
                fmt_link = self.fmt_link_wrap
            elif align == 'center':
                fmt_cell = self.fmt_center
                fmt_link = self.fmt_link_center
            else:
                fmt_cell = self.fmt_left
                fmt_link = self.fmt_link

            if link:
                sheet.write_url(row, col, link, fmt_link,
                                self.maybe_blank(text))
            elif type_ == 'string' or link is False or text == '':
                sheet.write_string(row, col, self.maybe_blank(text), fmt_cell)
            elif type_ in ('int', 'float', 'number', 'currency'):
                number = self.as_number(value)
                if number is None:
                    sheet.write_string(row, col,
                                       self.maybe_blank(text), fmt_cell)
                else:
                    if type_ == 'currency':
                        fmt_cell = self.fmt_currency
                    sheet.write_number(row, col, number, fmt_cell)
            else:
                sheet.write(row, col, self.maybe_blank(value), fmt_cell)

        if self.hard_blanks:
            sheet.write_string(row, col + 1, self.maybe_blank(''))
