"""Interface that collects data from the factory into flat variables."""


import asyncio
import logging
from collections import defaultdict
from functools import partial

logger = logging.getLogger(__name__)


def get_machine_vars(machine):
    def get_state(machine):
        machine_state_map = defaultdict(
            lambda: -1, {"off": 0, "on": 1, "production": 2, "error": 3}
        )
        return machine_state_map[machine.state]

    def get_planned_operating_time(machine):
        if (
            machine.schedule is not None
            and machine.schedule.active_block is not None
        ):
            action = machine.schedule.active_block.action
            return True if "switch-program" in action.__name__ else False
        else:
            return False

    # Status
    d = {}
    d["Status"] = {"func": partial(get_state, machine=machine), "val": -1}
    # Planned operating time
    d["PlannedOperatingTime"] = {
        "func": partial(get_planned_operating_time, machine=machine),
        "val": False,
    }
    d["Temperature"] = {"func": lambda: machine.temperature, "val": -1.0}
    d["ProductionInterruptCode"] = {
        "func": lambda: machine.production_interrupt_code,
        "val": 0,
    }
    d["Program"] = {"func": lambda: machine.program.uid, "val": "null"}

    return d


def get_program_vars(program):
    d = {}
    for name in program.consumption.keys():
        d[f"{name}.Consumption"] = {
            "func": lambda: program.consumption.get(name, 0),
            "val": 0,
        }
    for name in program.product_quantity.keys():
        d[f"{name}.ProductQuantity"] = {
            "func": lambda: program.product_quantity.get(name, 0),
            "val": 0,
        }
    for name in program.latest_material_id.keys():
        d[f"{name}.LatestMaterialId"] = {
            "func": lambda: program.latest_material_id.get(name, "null"),
            "val": "null",
        }

    return d


def get_container_vars(container):
    d = {}
    d["Level"] = {"func": lambda: container.level, "val": 0}
    return d


def get_vars_dict(factory):
    """Mapping from variable name to a function that gets the value."""
    d = {}
    # Machines
    for id_, machine in factory.machines.items():
        d.update(
            {
                f"{id_}.{name}": value
                for name, value in get_machine_vars(machine).items()
            }
        )

    # Consumable level
    for id_, container in factory.containers.items():
        d.update(
            {
                f"{id_}.{name}": value
                for name, value in get_container_vars(container).items()
            }
        )

    # Programs
    # NOTE: Assumes program be assigned to only one machine
    for id_, program in factory.programs.items():
        d.update(
            {
                f"{id_}.{name}": value
                for name, value in get_program_vars(program).items()
            }
        )

    # TODO: Quality control

    return d


async def update_vars(vars_dict):
    logger.info("Variable update loop started")
    while True:
        await asyncio.sleep(1)
        for var_name, d in vars_dict.items():
            value = d["func"]()
            if value is not None:
                await d["var"].write_value(value)
