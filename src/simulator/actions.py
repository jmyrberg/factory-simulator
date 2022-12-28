"""Schedules."""


from datetime import datetime, timedelta
from functools import partial, update_wrapper, wraps

import arrow
import simpy
from croniter import croniter

from src.simulator.base import Base
from src.simulator.issues import ScheduledMaintenanceIssue
from src.simulator.maintenance import Maintenance
from src.simulator.utils import AttributeMonitor


def get_action(name, *args, **kwargs):
    """Action called upon block start."""
    if "schedule" in kwargs:
        raise ValueError('Reserved kwarg "schedule" given in "kwargs"')

    funcs = {
        "switch-program": _action_switch_program,
        "maintenance": _action_maintenance,
    }
    func = partial(funcs[name], *args, **kwargs)
    # TODO: Cleanup the mess below
    args_str = ", ".join(args)
    kwargs_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    func_name = f"{name}("
    if len(args_str) > 0:
        func_name += args_str + ", "
    if len(kwargs_str) > 0:
        func_name += kwargs_str
    func_name += ")"
    func.__name__ = func_name
    return func


def _action_switch_program(block, program_id):
    # TODO: Simplify block/schedule events
    block.emit("action_started")
    machine = block.schedule.machine
    if machine is None or program_id is None:
        raise ValueError("Machine or program_id is None")

    programs = [p for p in machine.programs if p.uid == program_id]
    if len(programs) == 0:
        raise ValueError(f'Unknown program "{program_id}”')
    program = programs[0]

    if machine is not None and machine.state not in ["off", "error"]:
        block.env.process(machine._automated_program_switch(program))

    yield block.events["stopped"]
    if machine is not None and machine.state not in ["off", "on", "error"]:
        block.debug("Switching to on")
        block.env.process(machine._switch_on(priority=-2))

    block.emit("action_stopped")


def _action_maintenance(block):
    # TODO: Simplify block/schedule events
    block.emit("action_started")
    machine = block.schedule.machine
    maintenance = machine.maintenance
    duration = block.duration_hours * 60 * 60
    block.debug(f"Maintenance duration: {duration / 60 / 60} hours")
    issue = ScheduledMaintenanceIssue(machine, duration)
    block.env.process(maintenance.add_issue(issue))
    yield block.events["stopped"]
    block.emit("action_stopped")
