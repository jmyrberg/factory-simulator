"""Module for base object."""


import logging
import uuid
from datetime import timedelta

import arrow
import numpy as np
import pandas as pd

from src.simulator.utils import with_obj_monitor

logger = logging.getLogger(__name__)


class Base:
    def __init__(self, env, *args, **kwargs):
        self.env = env
        self.name = kwargs.get("name", "Unknown")
        self.uid = kwargs.get("uid") or f"{self.name}-{uuid.uuid4().hex[:8]}"

        # Internal
        self.tz = "Europe/Helsinki"

    def __repr__(self):
        return self.uid

    @property
    def data(self):
        if hasattr(self.env, "data"):
            return self.env.data
        else:
            raise ValueError("'data' does not exist in self.env")

    @property
    def data_df(self):
        flatten = [
            (*dkey, *dvalue)
            for dkey, dvalues in self.data.items()
            for dvalue in dvalues
        ]
        columns = ["dtype", "obj", "key", "ds", "value"]
        return pd.DataFrame(flatten, columns=columns)

    @property
    def data_last(self):
        return {
            k: v[-1] if len(v) > 0 else None for k, v in self.env.data.items()
        }

    @property
    def data_last_df(self):
        flatten = [
            (*dkey, dvalues[0]) for dkey, dvalues in self.data_last.items()
        ]
        columns = ["dtype", "obj", "key", "ds", "value"]
        return pd.DataFrame(flatten, columns=columns)

    def with_monitor(self, obj, pre=None, post=None, methods=None, name=None):
        return with_obj_monitor(
            obj=self,
            attr_obj=obj,
            pre=pre,
            post=post,
            methods=methods,
            name=name,
        )

    def append_data(self, dtype, key, value):
        dkey = (dtype, self.uid, key)
        dvalue = (self.now_dt.datetime, value)
        if self.monitor < 0:
            self.data[dkey].append(dvalue)
        elif self.monitor == 1:
            self.data[dkey] = [dvalue]
        elif self.monitor > 1:
            n = self.monitor - 1
            self.data[dkey] = self.data[dkey][-n:] + [dvalue]

    def emit(self, name, value=None, skip_log=False):
        if not skip_log:
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

    # Time utilities
    def minutes(self, seconds):
        return 60 * seconds

    def seconds(self, seconds):
        return seconds

    def hours(self, seconds):
        return self.minutes(60 * seconds)

    def days(self, seconds):
        return self.hours(24 * seconds)

    @property
    def randomize(self):
        if hasattr(self.env, "randomize"):
            return bool(self.env.randomize)
        else:
            return False  # Default

    @property
    def monitor(self):
        if hasattr(self.env, "monitor"):
            return self.env.monitor
        else:
            return 0  # Default

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

    # Randomized functions begin here
    def choice(self, choices, p=None):
        if self.randomize:
            return np.random.choice(choices, p=p)
        else:
            return choices[0]

    def uni(self, low, high):
        """Random float between [low, high]."""
        if self.randomize:
            return np.random.uniform(low, high)
        else:
            return (high + low) / 2

    def iuni(self, low, high, weights=None):
        """Random integer between [low, high]."""
        if weights is not None:
            choices = np.arange(low, high + 1)
            if self.randomize:
                return np.random.choice(choices, p=weights)
            else:
                return choices[np.argmax(weights)]
        else:
            if self.randomize:
                return np.random.randint(low, high)
            else:
                return int(round((high + low) / 2))

    def norm(self, mu, sigma, force_randomize=False):
        """Random number from normal distribution."""
        if self.randomize or force_randomize:
            return np.random.normal(mu, sigma)
        else:
            return mu

    def pnorm(self, mu, sigma, force_randomize=False):
        """Positive random number from normal distribution."""
        if self.randomize or force_randomize:
            return np.abs(
                self.norm(mu, sigma, force_randomize=force_randomize)
            )
        else:
            return np.abs(mu)

    def cnorm(self, low, high):
        """Random number from normal distribution confidence intervals."""
        # Consider (low, high) as 5/95% intervals
        pos = (self.norm(0, 1) - (-1.96)) / (1.96 * 2)
        return pos * (high - low) + low

    def jitter(self, max_ms=500):
        """Very small timespan."""
        if self.randomize:
            return self.uni(low=0, high=max_ms) / 1000
        else:
            return max_ms / 2 / 1000

    # Shortcuts for timeouts, "w" = wait
    def wjitter(self, max_ms=500):
        """Wait for a very small timespan."""
        return self.env.timeout(self.jitter(max_ms))

    def wnorm(self, low, high=None, scaler=1):
        """Wait based on normal distribution"""
        if high is None:
            wait_secs = max(self.norm(low, 0.01 * scaler), 0)
        else:
            wait_secs = max(self.cnorm(low, high), 0)

        return self.env.timeout(wait_secs)
