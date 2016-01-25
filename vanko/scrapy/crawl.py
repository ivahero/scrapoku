from scrapy.spiders.crawl import CrawlSpider
from scrapy.http import Request, HtmlResponse
from .spider import CustomSpider


class CustomCrawlSpider(CrawlSpider, CustomSpider):

    CrawlRequest = Request
    CrawlResponses = (HtmlResponse,)

    def make_custom_request(self, url, callback=None, dont_filter=False):
        return self.CrawlRequest(
            url=url, callback=callback, dont_filter=dont_filter)

    def make_requests_from_url(self, url):
        return self.make_custom_request(url, dont_filter=True)

    def _requests_to_follow(self, response):
        if not isinstance(response, self.CrawlResponses):
            return
        seen = set()
        for n, rule in enumerate(self._rules):
            links = [l for l in rule.link_extractor.extract_links(response)
                     if l not in seen]
            if links and rule.process_links:
                links = rule.process_links(links)
            for link in links:
                seen.add(link)
                r = self.make_custom_request(
                    url=link.url, callback=self._response_downloaded)
                r.meta.update(rule=n, link_text=link.text)
                yield rule.process_request(r)
