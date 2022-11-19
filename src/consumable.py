"""Machine programs."""


import logging

import arrow
import simpy
import uuid

from src.base import Base


logger = logging.getLogger(__name__)


class Consumable(Base):

    def __init__(self, env, content='raw-material', capacity=100, init=None):
        """Machine program."""
        super().__init__(env, name='Consumable')
        self.content = content
        self.container = simpy.Container(
            env,
            capacity=capacity,
            init=init or capacity
        )

    def fill_full(self):
        fill_amount = self.container.capacity - self.container.level
        yield from self.fill(fill_amount)

    def fill(self, amount):
        free = self.container.capacity - self.container.level
        fill_amount = free if amount > free else amount
        pct_fill = amount / self.container.capacity
        yield self.env.timeout(self.hours(1 * pct_fill))
        yield self.container.put(fill_amount)
        self.log(f'Filled {fill_amount}')

    def consume(self, amount):
        yield self.container.get(amount)
        self.log(f'Left in {self.name} container: {self.container.level:.2f}')
