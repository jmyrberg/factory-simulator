"""Module for base object."""


import logging
import uuid
from collections import defaultdict
from datetime import timedelta

import arrow
import numpy as np

from src.simulator.utils import with_obj_monitor

logger = logging.getLogger(__name__)


class Base:
    def __init__(self, env, *args, **kwargs):
        self.env = env
        self.name = kwargs.get("name", "Unknown")
        self.tz = "Europe/Helsinki"
        self.data = defaultdict(lambda: [])

        self.uid = kwargs.get("uid", f"{self.name}-{uuid.uuid4().hex[:8]}")

    def __repr__(self):
        return self.name

    def with_monitor(self, obj, pre=None, post=None, methods=None, name=None):
        return with_obj_monitor(
            obj=self,
            attr_obj=obj,
            pre=pre,
            post=post,
            methods=methods,
            name=name,
        )

    def emit(self, name, value=None):
        self.debug(f'Event - "{name}"')
        self.events[name].succeed(value)
        self.events[name] = self.env.event()

    def debug(self, message):
        self.log(message, level="debug")

    def info(self, message):
        self.log(message, level="info")

    def warning(self, message):
        self.log(message, level="warning")

    def error(self, message):
        self.log(message, level="error")

    def log(self, message, level="info"):
        ts = arrow.get(self.env.now).to(self.tz)
        ts_hki = ts.format("YYYY-MM-DD HH:mm:ss")
        getattr(logger, level)(f"{ts_hki} - {self.name} - {message}")

    def minutes(self, seconds):
        return 60 * seconds

    def seconds(self, seconds):
        return seconds

    def hours(self, seconds):
        return self.minutes(60 * seconds)

    def days(self, seconds):
        return self.hours(24 * seconds)

    @property
    def day(self):
        return self.now_dt.day

    @property
    def dow(self):
        return self.now_dt.weekday()

    @property
    def hour(self):
        return self.now_dt.hour

    @property
    def minute(self):
        return self.now_dt.minute

    @property
    def now_dt(self):
        return arrow.get(self.env.now).to(self.tz)

    @property
    def dtfmt(self):
        return "%Y-%m-%d %H:%M:%S"

    def time_until_time(self, clock_str):
        hour, minutes = clock_str.split(":")
        if self.time_passed_today(clock_str):
            days = 1
        else:
            days = 0
        target_dt = self.now_dt.replace(
            hour=int(hour), minute=int(minutes), second=0, microsecond=0
        ) + timedelta(days=days)
        return self.time_until(target_dt)

    def time_passed_today(self, clock_str):
        hour, minutes = clock_str.split(":")
        if self.hour < int(hour):
            return False
        elif self.hour == int(hour) and self.minute < int(minutes):
            return False
        else:
            return True

    def days_until(self, weekday):
        return (weekday - self.now_dt.weekday() + 7) % 7

    def time_until(self, target_dt):
        if target_dt < self.now_dt:
            raise ValueError(f"{target_dt} < {self.now_dt}")
        return (target_dt - self.now_dt).total_seconds()

    def uni(self, low, high):
        return np.random.uniform(low, high)

    def iuni(self, low, high, weights=None):
        if weights is not None:
            return np.random.choice(np.arange(low, high + 1), p=weights)
        else:
            return np.random.randint(low, high)

    def norm(self, mu, sigma):
        return np.random.normal(mu, sigma)

    def pnorm(self, mu, sigma):
        return np.abs(self.norm(mu, sigma))
