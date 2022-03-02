"""Module for scrapy pipelines."""


import logging

from scrapy import signals
from scrapy.exceptions import DropItem

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from crawler.db import get_database
from crawler.db_models import Listing


logger = logging.getLogger(__name__)


class BaseSqlitePipeline:

    def __init__(self, settings):
        self.sessions = {}

    @classmethod
    def from_crawler(cls, crawler):
        logger.info(f'Starting type {cls.__class__}')
        pipeline = cls(crawler.settings)
        crawler.signals.connect(pipeline.spider_opened, signals.spider_opened)
        crawler.signals.connect(pipeline.spider_closed, signals.spider_closed)
        return pipeline

    def spider_opened(self, spider):
        self.sessions[spider] = get_database()

    def spider_closed(self, spider):
        session = self.sessions.pop(spider)
        session.close()


class ListingLinkPipeline(BaseSqlitePipeline):

    def __init__(self, settings):
        super(ListingLinkPipeline, self).__init__(settings)

    def process_item(self, item, spider):
        session = self.sessions[spider]
        url = item['url']
        listing = session.query(Listing).filter_by(url=url).first()
        if listing is None:
            logger.debug(f'Adding listing URL "{url}"...')
            listing = Listing(**item)
            try:
                session.add(listing)
                session.commit()
                logger.info(f'Listing URL "{url}" added!')
            except:
                logger.warning(
                    'Failed to add listing URL "{url}", rolling back...')
                session.rollback()
                logger.warning('Rolled back successfully!')
        else:
            logger.info(f'Listing URL "{url}" already exists!')

        return DropItem


class ListingPipeline(BaseSqlitePipeline):

    def process_item(self, item, spider):
        session = self.sessions[spider]
        url = item['url']
        listing = session.query(Listing).filter_by(url=url).first()
        content_exists = listing is not None and listing.visited is not None
        try:
            mode = 'Changing' if content_exists else 'Adding'
            logger.debug(f'{mode} URL "{url}" listing content...')
            if listing:  # Change
                listing.visited = item['visited']
                listing.content = item['content']
            else:  # Add
                listing = Listing(**item)
                session.add(listing)
            session.commit()
            logger.info(f'{mode} URL "{url}" listing content done!')
        except:
            logger.error('Failed with URL "{url}", rolling back...')
            session.rollback()
            logger.error('Rolled back successfully!')

        return DropItem
