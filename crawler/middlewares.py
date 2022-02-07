"""Module for Scrapy middlewares."""


import logging

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.http import HtmlResponse

from crawler.request import SeleniumRequest
from crawler.utils import get_chromedriver


logger = logging.getLogger(__name__)


class SeleniumMiddleware:
    """Middleware that processes request with given callback.

    Headless mode can be disabled via ``DISABLE_HEADLESS`` Scrapy setting.
    """

    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls(crawler.settings)
        crawler.signals.connect(middleware.spider_opened,
                                signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed,
                                signals.spider_closed)
        return middleware

    def spider_opened(self, spider):
        self.driver = get_chromedriver(self.settings)

    def spider_closed(self, spider):
        if hasattr(self, 'driver'):
            self.driver.quit()

    def process_request(self, request, spider):
        logger.debug('Processing request with selenium')
        if not isinstance(request, SeleniumRequest):
            return None

        self.driver.get(request.url)
        driver_func = request.meta.get('driver_func')
        if driver_func is None:
            return HtmlResponse(
                self.driver.current_url,
                body=self.driver.page_source.encode('utf-8'),
                encoding='utf-8',
                request=request
            )
        else:
            logger.debug('Processing request with user given function')
            return driver_func(request, spider, self.driver)
