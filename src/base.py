"""Module for base object."""


import logging

import arrow


logger = logging.getLogger(__name__)


class Base:

    def __init__(self, env, *args, **kwargs):
        self.env = env
        self.name = kwargs.get('name', 'Unknown')

    def _trigger_event(self, name, value=None, keep_on=False):
        self.debug(f'Triggering event {name}')
        self.events[name].succeed(value)
        if not keep_on:
            self.events[name] = self.env.event()

    def debug(self, message):
        self.log(message, level='debug')

    def info(self, message):
        self.log(message, level='info')

    def warning(self, message):
        self.log(message, level='warning')

    def error(self, message):
        self.log(message, level='error')

    def log(self, message, level='info'):
        ts = arrow.get(self.env.now)
        ts_hki = ts.to('Europe/Helsinki').format('YYYY-MM-DD HH:mm:ss')
        getattr(logger, level)(f'{ts_hki} - {self.name:10.10s} - {message}')

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
