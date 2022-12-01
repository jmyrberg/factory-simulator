"""Factory."""


import logging

import arrow
import simpy
import uuid

from src.base import Base
from src.utils import with_resource_monitor


class Factory(Base):

    def __init__(self, env, name='raw-material', capacity=100.0, init=None):
        """Machine program."""
        super().__init__(env, name=f'Consumable({name})')
        self.name = name
        self.container = with_resource_monitor(simpy.Container(
            env=env,
            capacity=capacity,
            init=init or capacity
        ), 'container', self)

    def fill_full(self):
        fill_amount = self.container.capacity - self.container.level
        yield from self.fill(fill_amount)

    def fill(self, amount):
        free = self.container.capacity - self.container.level
        fill_amount = free if amount > free else amount
        pct_fill = amount / self.container.capacity
        yield self.env.timeout(self.hours(2 * pct_fill))
        yield self.container.put(fill_amount)
        self.log(f'Filled {fill_amount} / {self.container.capacity}')

    def consume(self, amount):
        yield self.container.get(amount)
        self.log(f'Container level: {self.container.level:.2f}')


class Material(Base):
    """For discrete materials with ID"""