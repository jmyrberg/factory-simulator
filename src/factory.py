"""Factory."""


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
    def from_config(cls, path: str):
        env = simpy.Environment(arrow.now('Europe/Helsinki').timestamp())
        cfg = parse_config(env, path)
        return cls(env, **cfg)

    def run(self, days=1):
        self.env.run(self.env.now + self.days(days))

    def plot(self):
        plot_factory(self)
