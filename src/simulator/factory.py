"""Factory."""


from typing import Dict

import arrow
import simpy

from src.simulator.base import Base
from src.simulator.bom import BOM
from src.simulator.consumable import Consumable
from src.simulator.containers import ConsumableContainer, MaterialContainer
from src.simulator.machine import Machine
from src.simulator.maintenance import Maintenance
from src.simulator.material import Material
from src.simulator.operator import Operator
from src.simulator.parser import parse_config
from src.simulator.plotting import plot_factory
from src.simulator.product import Product
from src.simulator.program import Program
from src.simulator.schedules import OperatingSchedule
from src.simulator.sensors import RoomTemperatureSensor, Sensor


class Factory(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        materials: Dict[str, Material] | None = None,
        consumables: Dict[str, Consumable] | None = None,
        products: Dict[str, Product] | None = None,
        containers: Dict[str, ConsumableContainer | MaterialContainer]
        | None = None,
        boms: Dict[str, BOM] | None = None,
        maintenance: Maintenance | None = None,
        programs: Dict[str, Program] | None = None,
        schedules: Dict[str, OperatingSchedule] | None = None,
        machines: Dict[str, Machine] | None = None,
        operators: Dict[str, Operator] | None = None,
        sensors: Dict[str, Sensor] | None = None,
        name: str = "factory",
        uid: str | None = None,
    ) -> None:
        """Factory."""
        super().__init__(env, name=name)

        # Inputs
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
        self.sensors = sensors or {}

        # Internal
        self.uid = uid
        self.add_sensor(RoomTemperatureSensor(env, self))

        self.env.factory = self  # Make Factory available everywhere
        self.env.factory_init_event.succeed()  # TODO: Rather 'global_events'

    def add_sensor(self, sensor):
        if sensor.uid not in self.sensors:
            self.sensors[sensor.uid] = sensor
            self.info(f'Added sensor "{sensor.uid}"')
        else:
            self.warning(f"Tried to add existing sensor {sensor.uid}")

    @classmethod
    def from_config(cls, path: str, real: bool = False):
        start = arrow.now("Europe/Helsinki").timestamp()
        if real:
            env = simpy.RealtimeEnvironment(start)
        else:
            env = simpy.Environment(start)

        env.factory_init_event = env.event()

        cfg = parse_config(env, path)
        return cls(env, **cfg)

    def run(self, days=None):
        until = None if days is None else self.env.now + self.days(days)
        self.env.run(until)

    def plot(self):
        plot_factory(self)
