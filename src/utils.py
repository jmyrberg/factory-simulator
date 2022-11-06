"""Utilities from time."""


import arrow


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
