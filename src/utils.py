"""Utilities from time."""


import arrow
import simpy

from functools import wraps, partial


class Monitor:
    """Monitor class attributes."""

    def __init__(self, dtype='categorical', value_func=None):
        self.dtype = dtype
        self.value_func = value_func

    def __set_name__(self, owner, name):
        self.public_name = name
        self.private_name = f'_{name}'

    def __get__(self, obj, objtype=None):
        value = getattr(obj, self.private_name)
        return value

    def __set__(self, obj, value):
        if hasattr(self, 'dtype'):
            obj.data[self.dtype].append((
                obj.now_dt.datetime,
                obj.name,
                self.public_name,
                self.value_func(value) if self.value_func else value
            ))
        else:
            obj.warning('Unknown dtype')
        setattr(obj, self.private_name, value)


def patch_resource(resource, pre=None, post=None):
    """Monitor simpy resources."""
    def get_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if pre:
                pre(resource)

            ret = func(*args, **kwargs)

            if post:
                post(resource)

            return ret
        return wrapper

    # Replace the original operations with our wrapper
    for name in ['put', 'get', 'request', 'release']:
        if hasattr(resource, name):
            setattr(resource, name, get_wrapper(getattr(resource, name)))


def with_resource_monitor(resource, resource_name, obj):
    def mfunc(resource, key_funcs, dtype='numerical'):
        for key, func in key_funcs:
            obj.data[dtype].append((
                obj.now_dt.datetime, obj.name,
                f'{resource_name}_{key}', func(resource)
            ))

    if isinstance(resource, simpy.Container):
        pre = partial(mfunc, key_funcs=[('pre_level', lambda x: x.level)])
        post = partial(mfunc, key_funcs=[('post_level', lambda x: x.level)])
    elif isinstance(resource, simpy.Resource):
        pre = None
        post = partial(mfunc, key_funcs=[
            ('post_queue', lambda x: len(x.queue)),
            ('post_users', lambda x: len(x.users)),
        ])
    elif isinstance(resource, (simpy.Store, simpy.PriorityStore)):
        pre = None
        post = partial(mfunc, key_funcs=[
            ('n_items', lambda x: len(x.items))
        ])
    else:
        raise NotImplementedError(f'Unknown type "{type(resource)}"')

    patch_resource(resource, pre, post)
    return resource


def ignore_causes(causes=None):
    if causes is None:
        causes = (simpy.resources.resource.Preempted,)
    elif not isinstance(causes, tuple):
        causes = tuple([causes])

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                yield from f(*args, **kwargs)
            except simpy.Interrupt as i:
                if isinstance(i.cause, causes):
                    self = args[0]
                    self.info(f'Interrupted: {self.name} - {f.__name__})')
                else:
                    raise i
        return wrapper
    return decorator


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
