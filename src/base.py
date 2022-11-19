"""Module for base object."""


import logging

import arrow

logger = logging.getLogger(__name__)


class Base:

    def __init__(self, env, *args, **kwargs):
        self.env = env
        self.name = kwargs.get('name', 'Unknown')

    def _trigger_event(self, name, value=None, keep_on=False):
        self.log(f'Triggering event {name}')
        self.events[name].succeed(value)
        if not keep_on:
            self.events[name] = self.env.event()

    def log(self, message):
        ts = arrow.get(self.env.now).format('YYYY-MM-DD HH:mm:ss')
        logger.info(f'{ts} - {self.name} - {message}')

    def minutes(self, seconds):
        return 60 * seconds

    def seconds(self, seconds):
        return seconds

    def hours(self, seconds):
        return self.minutes(60 * seconds)

    def days(self, seconds):
        return self, self.hours(24 * seconds)

    def time_until(self, **kwargs):
        curr_ts = arrow.get(self.env.now)
        target_ts = curr_ts.shift(**kwargs)
        return (target_ts - curr_ts).total_seconds()
