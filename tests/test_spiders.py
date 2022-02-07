"""Module for testing spiders."""


from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from crawler.spiders.listing_link import ListingSpider


def test_listing_spider():
    process = CrawlerProcess(get_project_settings())
    process.crawl(ListingSpider)
