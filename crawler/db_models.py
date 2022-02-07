"""Module for database models."""


from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from crawler.db import Base


class Listing(Base):
    __tablename__ = 'listings'

    url = Column(String, primary_key=True)
    created = Column(DateTime(timezone=True), server_default=func.now())
    visited = Column(DateTime(timezone=True))
    content = Column(String)
    
    def __repr__(self):
        return f'<Listing(url={self.url}>'