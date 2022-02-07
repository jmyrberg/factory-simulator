"""Module for database."""


import logging

from scrapy.utils.project import get_project_settings

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool


logger = logging.getLogger(__name__)

Base = declarative_base()


def get_database():
    engine = create_engine('sqlite:///./results/crawling.sqlite',
                           poolclass=NullPool)
    Base.metadata.bind = engine
    Base.metadata.create_all(engine, checkfirst=True)
    return sessionmaker(bind=engine)()
