"""Module for crawling listings and saving them into a database."""


import json
import logging

from datetime import datetime
from pytz import timezone

from scrapy import Spider, Request
from scrapy.exceptions import CloseSpider
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.loader import ItemLoader

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from crawler.db import get_database
from crawler.db_models import Listing


logger = logging.getLogger(__name__)


class ListingSpider(Spider):
    name = 'listing'
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'HTTPERROR_ALLOWED_CODES': [410, 404],
        'ITEM_PIPELINES': {
            'crawler.pipelines.ListingPipeline': 300
        }
    }

    def start_requests(self):
        self.session = get_database()
        # Find non-visited links
        rows = (
            self.session.query(Listing.url)
            .filter(Listing.visited.is_(None))
            .all()
        )
        logger.info(f'Number of listings to fetch: {len(rows)}')

        for row in rows:
            yield Request(row.url, callback=self.parse)

    def parse(self, resp):
        content = [{'status_code': resp.status}]

        if resp.status == 410:  # = Sold
            header_xpath = '//div[@class="listing-header"]//text()'
            inactive_xpath = '//div[@class="listing-inactive"]//text()'
            content.extend([
                {'header': resp.xpath(header_xpath).get()},
                {'inactive': resp.xpath(inactive_xpath).get()}
            ])
        elif resp.status == 404:  # = Gone
            main_xpath = '//main//text()'
            content.append({'main': resp.xpath(main_xpath).get()})
        else:
            # Title
            content.append({'title': resp.xpath('//title/text()').get()})

            # Overview
            overview_xpath = '//div[@class="listing-overview"]//text()'
            overview = []
            for p in resp.xpath(overview_xpath):
                overview.append(p.get().strip())
            content.append({'overview': overview})

            # Detail
            for detail in resp.xpath(
                    '//div[@class="details-grid__item-text"]'):
                k = detail.xpath('.//dt//text()').get()
                v = detail.xpath('.//dd//text()').get()
                content.append({k: v})

            # Info
            for info in resp.xpath('//div[@class="info-table__row"]'):
                k = info.xpath('.//dt//text()').get()
                v = info.xpath('.//dd//text()').get()
                content.append({k: v})

        return {
            'url': resp.url,
            'visited': datetime.now(timezone('Europe/Helsinki')),
            'content': json.dumps(content)
        }

    def closed(self, reason):
        if hasattr(self, 'session'):
            self.session.close()
