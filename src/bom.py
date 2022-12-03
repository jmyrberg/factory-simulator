"""Machine programs."""


import logging

import arrow
import simpy
import uuid

from src.base import Base
from src.utils import with_resource_monitor


class BOM(Base):

    def __init__(self, env, materials=None, consumables=None, products=None,
                 name='bill-of-material'):
        super().__init__(env, name=name)
        self.materials = materials or {}
        self.consumables = consumables or {}
        self.products = products or {}
