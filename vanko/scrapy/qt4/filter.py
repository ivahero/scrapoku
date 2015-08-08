from __future__ import print_function, absolute_import
from scrapy import FormRequest
from scrapy.dupefilters import RFPDupeFilter
import random

FP_SALT = 'abcdefghijklmnopqrstuvwxyz'


class FormAwareDupeFilter(RFPDupeFilter):
    def request_fingerprint(self, request):
        fingerprint = super(FormAwareDupeFilter, self). \
            request_fingerprint(request)
        if isinstance(request, FormRequest):
            fingerprint += '|' + ''.join(random.sample(FP_SALT, 20))
        return fingerprint
