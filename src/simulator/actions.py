"""Schedules."""


from functools import partial

from src.simulator.consumable import Consumable
from src.simulator.containers import (
    find_containers_by_type,
    put_into_consumable_containers,
    put_into_material_containers,
)
from src.simulator.issues import ScheduledMaintenanceIssue
from src.simulator.material import Material, MaterialBatch


def get_action(name, *args, **kwargs):
    """Action called upon block start."""
    if "schedule" in kwargs:
        raise ValueError('Reserved kwarg "schedule" given in "kwargs"')

    funcs = {
        "switch-program": _action_switch_program,
        "maintenance": _action_maintenance,
        "procurement": _action_procurement,
    }
    orig_func = funcs[name]
    func = partial(orig_func, *args, **kwargs)
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


def _action_procurement(block, content_uid, quantity):
    # TODO: Fail probability
    block.emit("action_started")
    # Find material or consumable object
    factory = block.env.factory
    content = factory.find_uid(content_uid)
    containers = find_containers_by_type(content, factory.containers.values())
    yield block.env.timeout(60)  # TODO: Do properly and kill active block
    if isinstance(content, Material):
        batch = MaterialBatch(
            env=block.env,
            material=content,
            quantity=quantity,
            created_ts=block.now_dt.shift(hours=block.iuni(-90, -7)),
        )
        _, total_put = yield from put_into_material_containers(
            batches=[batch], containers=containers, strategy="first"
        )
    elif isinstance(content, Consumable):
        total_put = yield from put_into_consumable_containers(
            quantity=quantity, containers=containers, strategy="first"
        )
    else:
        raise ValueError(
            f"Unknown content type '{type(content)}' for procurement"
        )
    block.emit("action_stopped", value=total_put)


def _action_switch_program(block, program_id):
    # TODO: Simplify block/schedule events
    block.emit("action_started")
    machine = block.schedule.machine

    if machine is None or program_id is None:
        raise ValueError("Machine or program_id is None")

    machine.is_planned_operating_time = True

    programs = [p for p in machine.programs if p.uid == program_id]
    if len(programs) == 0:
        raise ValueError(f'Unknown program "{program_id}”')
    program = programs[0]

    if machine is not None and machine.state not in ["off", "error"]:
        block.env.process(machine._automated_program_switch(program))

    yield block.events["stopped"]

    machine.is_planned_operating_time = False

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

    machine.is_planned_operating_time = False

    block.debug(f"Maintenance duration: {duration / 60 / 60} hours")
    issue = ScheduledMaintenanceIssue(machine, duration)
    block.env.process(maintenance.add_issue(issue))

    yield block.events["stopped"]
    block.emit("action_stopped")
