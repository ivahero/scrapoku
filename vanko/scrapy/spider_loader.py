from scrapy.spiderloader import SpiderLoader


class CustomSpiderLoader(SpiderLoader):
    def load(self, spider_name):
        if spider_name != '.':
            return super(CustomSpiderLoader, self).load(spider_name)
        if len(self._spiders) == 1:
            return self._spiders[self._spiders.keys()[0]]
        if self._spiders:
            raise KeyError('Multiple spiders found: %s' %
                           sorted(self._spiders.keys()))
        raise KeyError('No spiders loaded')
