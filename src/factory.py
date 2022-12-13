"""Factory."""


import asyncio

from typing import Dict

import arrow
import simpy

from src.base import Base
from src.bom import BOM
from src.containers import ConsumableContainer, MaterialContainer
from src.consumable import Consumable
from src.machine import Machine
from src.maintenance import Maintenance
from src.material import Material
from src.operator import Operator
from src.parser import parse_config
from src.plotting import plot_factory
from src.product import Product
from src.program import Program
from src.schedules import OperatingSchedule


class Factory(Base):

    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        materials: Dict[str, Material] | None = None,
        consumables: Dict[str, Consumable] | None = None,
        products: Dict[str, Product] | None = None,
        containers: Dict[str, ConsumableContainer | MaterialContainer] | None = None,
        boms: Dict[str, BOM] | None = None,
        maintenance: Maintenance | None = None,
        programs: Dict[str, Program] | None = None,
        schedules: Dict[str, OperatingSchedule] | None = None,
        machines: Dict[str, Machine] | None = None,
        operators: Dict[str, Operator] | None = None,
        name='factory'
    ) -> None:
        """Factory."""
        super().__init__(env, name=name)
        self.env.factory = self  # Make Factory available everywhere
        self.materials = materials
        self.consumables = consumables
        self.products = products
        self.containers = containers
        self.boms = boms
        self.maintenance = maintenance
        self.programs = programs
        self.schedules = schedules
        self.machines = machines
        self.operators = operators

    @classmethod
    def from_config(cls, path: str, real: bool = False):
        start = arrow.now('Europe/Helsinki').timestamp()
        if real:
            env = simpy.RealtimeEnvironment(start)
        else:
            env = simpy.Environment(start)
        cfg = parse_config(env, path)
        return cls(env, **cfg)

    def run(self, days=None):
        until = None if days is None else self.env.now + self.days(days)
        self.env.run(until)

    def get_vars_dict(self):
        # TODO: Separate module for this
        d = {}
        # Machines
        for id_, machine in self.machines.items():
            d[f'{id_}.program'] = {
                'func': lambda: machine.program.name,
                'val': 'None'
            }
            d[f'{id_}.state'] = {
                'func': lambda: machine.state,
                'val': 'None'
            }
            d[f'{id_}.production_interruption_ongoing'] = {
                'func': lambda: machine.production_interruption_ongoing,
                'val': False
            }
            d[f'{id_}.room_temperature'] = {
                'func': lambda: machine.room_temperature,
                'val': -1.0
            }
            d[f'{id_}.temperature'] = {
                'func': lambda: machine.temperature,
                'val': -1.0
            }

        return d

    async def update_vars(self, vars_dict):
        self.info('Updating variables')
        while True:
            await asyncio.sleep(1)
            for var_name, d in vars_dict.items():
                value = d['func']()
                self.debug(f'Setting {var_name} value: {value!r}')

                if value is not None:
                    await d['var'].write_value(value)

    def plot(self):
        plot_factory(self)
