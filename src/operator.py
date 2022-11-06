"""Models operator."""


import logging

import arrow

from src.base import Base


logger = logging.getLogger(__name__)


class Operator(Base):

    def __init__(self, env):
        super().__init__(env, name='Operator')
        self.env = env
        self.state = 'home'
        self.machine = None

        self.data = []

        self.env.process(self.home())

    def assign_machine(self, machine):
        self.machine = machine
        return self

    def _get_next_work_arrival(self):
        ts = arrow.get(self.env.now)
        if ts.weekday in (5, 6):
            days = 7 - ts.weekday
        else:
            days = 0 if ts.hour < 8 else 1

        next_day = ts.day + days
        next_hour = 8
        next_minute = 0
        arrival = ts.replace(
            day=next_day, hour=next_hour, minute=next_minute)
        # self.log(f'Arrival: {arrival}')
        return arrival.timestamp() - self.env.now

    def home(self):
        self.log('Chilling at home...')
        yield self.env.timeout(self._get_next_work_arrival())
        self.log('Going to work...')
        yield self.env.process(self.work())

    def work(self):
        self.log('Working...')
        self.log('Turning machine on...')
        self.machine.switch_on()
        self.log('Turning program on...')
        self.machine.program = 1
        yield self.env.timeout(self.hours(3.5))  # FIXME: Randomize

        # Go to lunch
        # TODO: Wait for batch to finish
        self.log('Going to lunch...')
        self.machine.switch_off()
        had_lunch = self.env.process(self.lunch())
        yield had_lunch

        # Continue working
        self.log('Continuing working...')
        self.machine.switch_on()
        yield self.env.timeout(self.hours(4))  # FIXME: Randomize

        self.log('Going home...')
        self.machine.switch_off()
        self.env.process(self.home())

    def lunch(self):
        self.log('Eating lunch...')
        yield self.env.timeout(self.minutes(30))  # FIXME: Randomize
        self.log('Lunch done!')
