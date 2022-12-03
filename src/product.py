"""Machine programs."""


import logging

import arrow
import simpy
import uuid

from src.base import Base
from src.utils import with_resource_monitor


class Product(Base):

    def __init__(self, env, name='product'):
        """Machine program."""
        super().__init__(env, name=name)
        self.name = name
