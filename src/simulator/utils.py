"""Helper functions and classes."""


from collections import UserDict, UserList
from functools import partial, wraps
from typing import Callable, Tuple

import simpy
from simpy.resources.resource import Preempted

from src.simulator.causes import BaseCause

InterruptType = Preempted | BaseCause
CauseType = Tuple[InterruptType] | InterruptType | None


class AttributeMonitor:
    """Monitor class attributes."""

    def __init__(self, dtype="categorical", value_func=None, name=None):
        self.dtype = dtype
        self.value_func = value_func
        self.name = name

    def __set_name__(self, owner, name):
        self.public_name = name if self.name is None else self.name
        self.private_name = f"_{name}"

    def __get__(self, obj, objtype=None):
        value = getattr(obj, self.private_name)
        return value

    def __set__(self, obj, value):
        if hasattr(self, "dtype"):
            obj.data[self.dtype].append(
                (
                    obj.now_dt.datetime,
                    obj.name,
                    self.public_name,
                    self.value_func(value) if self.value_func else value,
                )
            )
        else:
            obj.warning("Unknown dtype")
        setattr(obj, self.private_name, value)


class MonitoredList(UserList):
    """List whose methods can be patched for monitoring purposes."""


class MonitoredDict(UserDict):
    """Dict whose methods can be patched for monitoring purposes."""


def copy_class(cls):
    return type(cls.__name__, cls.__bases__, dict(cls.__dict__))


def patch_obj(obj, pre=None, post=None, methods=None):
    """Patch custom classes for data collection."""
    # Methods to be patched, if not given
    if methods is None and isinstance(obj, list):
        methods = [
            "insert",
            "append",
            "__setitem__",
            "__delitem__",
            "remove",
            "pop",
        ]
    elif methods is None and isinstance(obj, dict):
        methods = [
            "__setitem__",
            "__delitem__",
            "pop",
            "update",
            "popitem",
            "setdefault",
            "clear",
        ]
    elif methods is None:
        methods = ["put", "get", "request", "release"]

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

    # For dict and list, we must patch custom classes before init
    if isinstance(obj, dict):
        cls = copy_class(MonitoredDict)
    elif isinstance(obj, list):
        cls = copy_class(MonitoredList)
    else:
        cls = None

    # Replace the original class/instance methods with wrapped one
    obj_or_cls = obj if cls is None else cls
    for method in methods:
        if hasattr(obj_or_cls, method):
            wrapper = get_wrapper(getattr(obj_or_cls, method))
            setattr(obj_or_cls, method, wrapper)

    # Create an instance from the patched class
    if cls is not None:
        obj = obj_or_cls(obj)

    return obj


def with_obj_monitor(
    obj, attr_obj, pre=None, post=None, methods=None, name=None
):
    """Monitor any object."""
    name = name or str(attr_obj)

    def mfunc(attr_obj, key_funcs):
        # (metric_name, func, dtype(optional))
        for tup in key_funcs:
            if len(tup) == 2:
                key, func = tup
                dtype = "numerical"  # = default
            elif len(tup) == 3:
                key, func, dtype = tup

            obj.data[dtype].append(
                (
                    obj.now_dt.datetime,
                    obj.name,
                    f"{name}_{key}",
                    func(attr_obj),
                )
            )

    # Functions to apply
    if pre is not None or post is not None:
        pre = partial(mfunc, key_funcs=pre) if pre is not None else None
        post = partial(mfunc, key_funcs=post) if post is not None else None
    elif isinstance(attr_obj, simpy.Container):
        pre = partial(mfunc, key_funcs=[("pre_level", lambda x: x.level)])
        post = partial(mfunc, key_funcs=[("post_level", lambda x: x.level)])
    elif isinstance(attr_obj, simpy.Resource):
        pre = None
        post = partial(
            mfunc,
            key_funcs=[
                ("post_queue", lambda x: len(x.queue)),
                ("post_users", lambda x: len(x.users)),
            ],
        )
    elif isinstance(attr_obj, (simpy.Store, simpy.PriorityStore)):
        pre = None
        post = partial(mfunc, key_funcs=[("n_items", lambda x: len(x.items))])
    elif isinstance(attr_obj, (list)):
        pre = None
        post = partial(mfunc, key_funcs=(("length", lambda x: len(x.items))))
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
                        f'Interrupted process "{f.__name__}" due to "{i}"'
                    )
                else:
                    raise i

        return wrapper

    return decorator


def wait_factory(func):
    """Decorator to wait until factory is available in `self.env`."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        assert isinstance(
            self.env, (simpy.Environment, simpy.RealtimeEnvironment)
        )
        if not hasattr(self.env, "factory"):
            yield self.env.factory_init_event
            self.debug("Waiting for factory init event")

        yield from func(*args, **kwargs)

    return wrapper
