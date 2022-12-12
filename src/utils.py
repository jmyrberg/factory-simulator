"""Helper functions and classes."""


from collections import defaultdict
from functools import wraps, partial
from typing import Callable, Tuple

import simpy

from simpy.resources.resource import Preempted

from src.causes import BaseCause


InterruptType = Preempted | BaseCause
CauseType = Tuple[InterruptType] | InterruptType | None


class AttributeMonitor:
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


class MonitoredList(list):
    """List whose methods can be patched for monitoring."""


def patch_obj(obj, pre=None, post=None, methods=None):
    """Patch simpy objs for data collection."""
    if methods is None and isinstance(obj, list):
        methods = ['insert', 'append', '__setitem__', '__delitem__', 'remove']
    elif methods is None:
        methods = ['put', 'get', 'request', 'release']

    def get_wrapper(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if pre:
                pre(obj)

            ret = func(*args, **kwargs)

            if post:
                post(obj)

            return ret
        return wrapper

    # Replace the original operations with our wrapper
    for method in methods:
        if hasattr(obj, method):
            setattr(obj, method, get_wrapper(getattr(obj, method)))

    return obj


def with_obj_monitor(obj, attr_obj, pre=None, post=None,
                     methods=None, name=None):
    """Monitor any object."""
    name = name or str(attr_obj)

    def mfunc(attr_obj, key_funcs):
        # (metric_name, func, dtype(optional))
        for tup in key_funcs:
            if len(tup) == 2:
                key, func = tup
                dtype = 'numerical'  # = default
            elif len(tup) == 3:
                key, func, dtype = tup

            obj.data[dtype].append((
                obj.now_dt.datetime, obj.name,
                f'{name}_{key}', func(attr_obj)
            ))

    # Functions to apply
    if pre is not None or post is not None:
        if pre is not None:
            pre = partial(mfunc, key_funcs=pre)
        if post is not None:
            post = partial(mfunc, key_funcs=post)
    elif isinstance(attr_obj, simpy.Container):
        pre = partial(mfunc, key_funcs=[('pre_level', lambda x: x.level)])
        post = partial(mfunc, key_funcs=[('post_level', lambda x: x.level)])
    elif isinstance(attr_obj, simpy.Resource):
        pre = None
        post = partial(mfunc, key_funcs=[
            ('post_queue', lambda x: len(x.queue)),
            ('post_users', lambda x: len(x.users)),
        ])
    elif isinstance(attr_obj, (simpy.Store, simpy.PriorityStore)):
        pre = None
        post = partial(mfunc, key_funcs=[
            ('n_items', lambda x: len(x.items))
        ])
    elif isinstance(attr_obj, (list)):
        pre = None
        post = partial(mfunc, key_funcs=(
            ('length', lambda x: len(x.items))
        ))
    else:
        raise NotImplementedError(f'Unknown type "{type(attr_obj)}"')

    return patch_obj(attr_obj, pre, post, methods=methods)


def ignore_causes(causes: CauseType = None) -> Callable:
    """Decorator to ignore simpy interrupts from certain causes.

    Args:
        causes (optional): Cause types to ignore if process is interrupted.

    Examples:

        @ignore_causes(WorkStoppedCause)
        def process_func(env, ...):
            while True:
                yield do_something()
    """
    if causes is None:
        causes = (Preempted,)
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
                    self.debug(
                        f'Interrupted process "{f.__name__}" due to "{i}"')
                else:
                    raise i
        return wrapper
    return decorator
