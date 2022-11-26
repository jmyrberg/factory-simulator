"""Utilities from time."""


import arrow
import simpy


def ignore_preempted(f):
    def wrapper(*args, **kwargs):
        try:
            yield from f(*args, **kwargs)
        except simpy.Interrupt as i:
            if isinstance(i.cause, simpy.resources.resource.Preempted):
                self = args[0]
                self.info(f'INTERRUPTED: {self.name} - {f.__name__})')
            else:
                raise i
    return wrapper


def minutes(seconds):
    return 60 * seconds


def seconds(seconds):
    return seconds


def hours(seconds):
    return minutes(60 * seconds)


def days(seconds):
    return hours(24 * seconds)


def time_until(env, **kwargs):
    curr_ts = arrow.get(env.now)
    target_ts = curr_ts.shift(**kwargs)
    return (target_ts - curr_ts)
