from __future__ import print_function, absolute_import
import logging
import scrapy
from scrapy.exceptions import IgnoreRequest
from scrapy.shell import inspect_response


class LoginFailed(IgnoreRequest):
    pass


class LoginSpider(scrapy.Spider):

    def __init__(self, *a, **kw):
        params = 'login_debug login_verbose login_url logout_url \
                  username_field username passwd_field passwd \
                  login_check login_data allow_second_login'.split()
        vals = dict(
            (arg, kw.pop(arg) if arg in kw else getattr(self, arg, None))
            for arg in params)
        super(LoginSpider, self).__init__(*a, **kw)
        for name in vals:
            setattr(self, name, vals[name])
        self.in_first_attempt = True
        self.logged_in = False

    def start_requests(self):
        if self.logged_in or not self.login_url:
            self.verbose('original urls')
            return super(LoginSpider, self).start_requests()
        else:
            self.verbose('get into form')
            return [self.get_login_request()]

    def verbose(self, msg):
        if self.login_verbose:
            logging.debug('[login]: ' + msg)

    def get_login_request(self):
        return scrapy.Request(self.login_url,
                              callback=self.pre_login,
                              dont_filter=True)

    def pre_login(self, response):
        if self.login_debug:
            inspect_response(response, self)
        formdata = dict()
        if self.login_data:
            formdata.update(self.login_data)
        formdata[self.username_field] = self.username or ''
        formdata[self.passwd_field] = self.passwd or ''
        self.verbose('final: %s' % formdata)
        yield scrapy.FormRequest.from_response(response,
                                               formdata=formdata,
                                               callback=self.submit_login,
                                               dont_filter=True)

    def submit_login(self, response):
        if self.logged_in:
            self.verbose('already logged in')
        elif self.login_check in response.body_as_unicode():
            self.verbose('logged in successfully')
            self.logged_in = True
            for req in self.start_requests():
                yield req
            self.verbose('bye')
        else:
            if self.allow_second_login and self.in_first_attempt:
                self.verbose('need another attempt..')
            else:
                self.verbose('login failed')
            if self.login_debug:
                inspect_response(response, self)
            if self.allow_second_login and self.in_first_attempt:
                self.in_first_attempt = False
                yield self.get_login_request()
            else:
                raise LoginFailed(response)
