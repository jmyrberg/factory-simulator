"""Factory."""


from collections import defaultdict
from typing import Dict

import arrow
import simpy

from src.simulator.base import Base
from src.simulator.bom import BOM
from src.simulator.consumable import Consumable
from src.simulator.containers import ConsumableContainer, MaterialContainer
from src.simulator.exporters import Exporter
from src.simulator.machine import Machine
from src.simulator.maintenance import Maintenance
from src.simulator.material import Material
from src.simulator.operator import Operator
from src.simulator.parser import parse_config
from src.simulator.plotting import plot_numerical, plot_timeline
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
        exporters: Dict[str, Exporter] | None = None,
        randomize: bool = True,
        monitor: int = 100,
        name: str = "factory",
        uid: str | None = None,
    ) -> None:
        """Factory."""
        super().__init__(env, uid=uid, name=name)

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
        self.exporters = exporters or {}

        # Internal
        self._state = {}
        self.add_sensor(
            RoomTemperatureSensor(
                env, self, uid=f"{self.uid}-room-temperature-sensor"
            )
        )

        # Only factory is allowed to touch env
        self.env.factory = self  # Make Factory available everywhere
        self.env.randomize = randomize
        self.env.monitor = monitor
        self.env.factory_init_event.succeed()  # TODO: Rather 'global_events'

    @property
    def state(self):
        statedict = {
            f"{uid}.{key}": v
            for (dtype, uid, key), (ds, v) in self.data_last.items()
        }
        statedict[f"{self.uid}.datetime"] = self.now_dt.datetime
        return statedict

    def add_sensor(self, sensor):
        if sensor.uid not in self.sensors:
            self.sensors[sensor.uid] = sensor
            self.info(f'Added sensor "{sensor.uid}"')
        else:
            self.warning(f"Tried to add existing sensor {sensor.uid}")

    def find_uid(self, uid):
        for attr in [
            "materials",
            "consumables",
            "products",
            "machines",
            "operators",
            "containers",
            "maintenance",
            "programs",
            "schedules",
            "sensors",
        ]:
            objs = getattr(self, attr)
            if isinstance(objs, dict) and uid in objs:
                return objs[uid]

        raise KeyError(f'UID "{uid}" not found')

    @staticmethod
    def init_env(env):
        env.factory_init_event = env.event()
        env.data = defaultdict(lambda: [])
        return env

    @classmethod
    def from_config(cls, path: str, real: bool = False):
        start = arrow.now("Europe/Helsinki").timestamp()
        if real:
            env = simpy.RealtimeEnvironment(start)
        else:
            env = simpy.Environment(start)

        env = Factory.init_env(env)

        cfg = parse_config(env, path)
        return cls(env, **cfg)

    def run(self, days=None):
        until = None if days is None else self.env.now + self.days(days)
        self.env.run(until)

    def plot(self):
        end_dt = self.now_dt.datetime
        plot_timeline(
            df=self.data_df.query("dtype == 'categorical'"),
            end_dt=end_dt,
            width=800,
        )
        plot_numerical(
            df=self.data_df.query("dtype == 'numerical'"),
            end_dt=end_dt,
            width=800,
        )
