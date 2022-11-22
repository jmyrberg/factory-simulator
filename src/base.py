"""Module for base object."""


import logging

import arrow
import numpy as np


logger = logging.getLogger(__name__)


class Base:

    def __init__(self, env, *args, **kwargs):
        self.env = env
        self.name = kwargs.get('name', 'Unknown')
        self.tz = 'Europe/Helsinki'

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
        ts = arrow.get(self.env.now).to(self.tz)
        ts_hki = ts.format('YYYY-MM-DD HH:mm:ss')
        getattr(logger, level)(f'{ts_hki} - {self.name} - {message}')

    def minutes(self, seconds):
        return 60 * seconds

    def seconds(self, seconds):
        return seconds

    def hours(self, seconds):
        return self.minutes(60 * seconds)

    def days(self, seconds):
        return self, self.hours(24 * seconds)

    @property
    def now_dt(self):
        return arrow.get(self.env.now).to(self.tz)

    def time_until(self, target_dt):
        if target_dt < self.now_dt:
            raise ValueError(f'{target_dt} < {self.now_dt}')
        return (target_dt - self.now_dt).total_seconds()

    def norm(self, mu, sigma):
        return np.random.normal(mu, sigma)

    def pnorm(self, mu, sigma):
        return np.abs(self.norm(mu, sigma))
