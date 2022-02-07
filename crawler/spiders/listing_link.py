"""Module for crawling listings and saving them into a database."""


import logging
import math

from datetime import datetime
from pytz import timezone

import pandas as pd

from scrapy import Spider, Request
from scrapy.exceptions import CloseSpider
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor
from scrapy.loader import ItemLoader

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from sqlalchemy import func

from crawler.db import get_database
from crawler.db_models import Listing
from crawler.request import SeleniumRequest
from crawler.utils import get_chromedriver


logger = logging.getLogger(__name__)


class ListingLinkSpider(Spider):
    name = 'listing-link'
    base_url = 'https://asunnot.oikotie.fi/myytavat-asunnot?pagination='
    listing_link_extractor = LinkExtractor(
        attrs=('href', 'ng-href'),
        allow_domains=('asunnot.oikotie.fi'),
        allow=(rf'.*/myytavat-asunnot/.*/[0-9]+'),
        deny=(r'.*?origin\=.*'),
        deny_domains=(),
        canonicalize=True
    )
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        'ITEM_PIPELINES': {
            'crawler.pipelines.ListingLinkPipeline': 300
        },
        'DOWNLOADER_MIDDLEWARES': {
            'crawler.middlewares.SeleniumMiddleware': 800
        }
    }

    def start_requests(self):
        # Listing stats
        avg_listing_days = 14
        listings_per_page = 24
        avg_listings = 40_000
        avg_pages = avg_listings / listings_per_page
        avg_pages_per_day = avg_pages / avg_listing_days

        # Check the latest creation date
        self.session = get_database()
        row = self.session.query(func.max(Listing.created)).first()
        if row is not None:
            latest_created = pd.to_datetime(row[0])
        else:
            latest_created = pd.to_datetime('1990-01-01')
        
        now = pd.to_datetime(datetime.utcnow())
        days_since = (now - latest_created).total_seconds() / 60 / 60 / 24
        last_calc_page = int(math.ceil(days_since * avg_pages_per_day))
        last_existing_page = self._get_pagination_urls()
        logger.info(f'Last calculated page to fetch: {last_calc_page}')
        logger.info(f'Last existing page: {last_existing_page}')
        last_page = max(min(last_calc_page, last_existing_page), 10)
        logger.info(f'Fetching pages until: {last_page}')

        # Fetch pagination links
        for page in range(1, last_page):
            yield SeleniumRequest(
                f'{self.base_url}{page}',
                driver_func=self._handle_pagination_page,
                callback=self.parse,
                priority=last_page - page
            )

    def _get_pagination_urls(self):
        # TODO: SeleniumRequest instead of self.driver
        self.driver = get_chromedriver(settings=self.settings)
        self.driver.get(f'{self.base_url}1')

        # Accept cookies modal
        self._handle_modal()

        # Get the last page available
        last_page = self._get_last_page()

        self.driver.quit()

        return int(last_page)

    def _handle_modal(self):
        # Find iframe
        logger.info('Waiting for iframe...')
        iframe_xpath = "//iframe[contains(@id, 'sp_message_iframe')]"
        iframe = WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.XPATH, iframe_xpath)))
        self.driver.switch_to.frame(iframe)
        logger.info(f'Switched to iframe {iframe}')

        # Find button
        logger.info('Finding button...')
        button_xpath = "//button[contains(., 'Hyväksy')]"
        WebDriverWait(self.driver, 5).until(
            EC.presence_of_element_located((By.XPATH, button_xpath)))
        modal = self.driver.find_element_by_xpath(button_xpath)
        logger.info('Clicking modal...')
        modal.click()
        logger.info('Waiting 1 second...')
        self.driver.implicitly_wait(1)
        logger.info('Waiting for modal to disappear...')
        WebDriverWait(self.driver, 10).until(
            EC.invisibility_of_element_located((By.XPATH, button_xpath)))

        logger.info('Switching to default frame')
        self.driver.switch_to.default_content()
        logger.info('Modal handled successfully!')

    def _get_last_page(self):
        logger.info('Getting last page...')
        last_page_xpath = '//span[contains(@ng-bind, "ctrl.totalPages")]'
        last_page_element = self.driver.find_element_by_xpath(last_page_xpath)
        last_page = int(last_page_element.text.split('/')[-1].strip())
        logger.info(f'Last page found: {last_page}')
        return last_page

    @staticmethod
    def _handle_pagination_page(request, spider, driver):
        listings_xpath = '//div[contains(@class, "cards__card ng-scope")]'
        driver.execute_script("window.scrollTo(0,document.body.scrollHeight)")
        WebDriverWait(driver, 5).until(
            EC.presence_of_all_elements_located((By.XPATH, listings_xpath)))
        driver.implicitly_wait(0.5)

        return HtmlResponse(
            driver.current_url,
            body=driver.page_source.encode('utf-8'),
            encoding='utf-8',
            request=request
        )

    def parse(self, resp):
        listing_links = self.listing_link_extractor.extract_links(resp)
        for link in listing_links:
            yield {'url': link.url}

    def closed(self, reason):
        if hasattr(self, 'driver'):
            self.driver.quit()
