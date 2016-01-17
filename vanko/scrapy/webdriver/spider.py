from ..spider import CustomSpider
from .response import WebdriverResponseMixin
from .wrapper import WebdriverWrapper


class WebdriverSpiderMixin(WebdriverResponseMixin):

    def webdriver_loglevel(self, new_level=None, default=None):
        return WebdriverWrapper.webdriver_loglevel(
            self.settings, new_level, default)

    def opened(self):
        self.wrapper = WebdriverWrapper(self.settings)
        self.webdriver = None
        super(WebdriverSpiderMixin, self).opened()

    def run_action(self, action):
        if action == 'crawl':
            self.webdriver = self.wrapper.open(
                implicitly_wait=self.implicitly_wait, spider=self)
        super(WebdriverSpiderMixin, self).run_action(action)

    def closed(self, reason):
        self.wrapper.close()
        self.webdriver = None
        super(WebdriverSpiderMixin, self).closed(reason)


class WebdriverSpider(WebdriverSpiderMixin, CustomSpider):
    pass
