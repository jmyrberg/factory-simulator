"""Factory is the main interface towards the end-user."""


from collections import defaultdict
from typing import Dict, TypeVar

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

FactoryType = TypeVar("FactoryType", bound="Factory")


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
        collectors: Dict[str, dict] | None = None,
        exporters: Dict[str, Exporter] | None = None,
        randomize: bool = True,
        monitor: int = 100,
        name: str = "factory",
        uid: str | None = None,
    ) -> None:
        """Factory object.

        Args:
            env: Simpy environment object.
            materials (optional): Materials used within the factory. Should be
                a dictionary that maps UID -> Material, e.g.
                {
                    "material1": Material
                }
                Defaults to None.
            consumables (optional): Consumables used within the factory. Should
                be a dictionary that maps UID -> Consumable, e.g.
                {
                    "consumable1": Consumable
                }
                Defaults to None.
            products (optional): Products produced by the factory. Should
                be a dictionary that maps UID -> Product, e.g.
                {
                    "product1": Product
                }
                Defaults to None.
            containers (optional): Containers within the factory. Should
                be a dictionary that maps UID ->
                {Material,Consumable,Product}Container, e.g.
                {
                    "materialcontainer1": MaterialContainer,
                    "consumablecontainer1": ConsumableContainer,
                    "productcontainer1": ProductContainer
                }
                Defaults to None.
            boms (optional): Bill of materials used by the factory machines.
                Should be a dictionary that maps UID -> BOM, e.g.
                {
                    "bom1": BOM
                }
                Defaults to None.
            maintenance (optional): Maintenance team used by the factory.
                Should be a dictionary that maps UID -> Maintenance, e.g.
                {
                    "maintenance1": Maintenance
                }
                Defaults to None.
            programs (optional): Machine programs used by the factory. Should
                be a dictionary that maps UID -> Program, e.g.
                {
                    "program1": Program
                }
                Defaults to None.
            schedules (optional): Schedules used by the factory. Should be a
                dictionary that maps UID -> {Operating,Procurement}Schedule,
                e.g.
                {
                    "operating-schedule1": OperatingSchedule,
                    "procurement-schedule1": ProcurementSchedule
                }
                Defaults to None.
            machines (optional): Machines in the factory. Should be a
                dictionary that maps UID -> Machine,
                e.g.
                {
                    "machine1": Machine
                }
                Defaults to None.
            operators (optional): Operators in the factory. Should be a
                dictionary that maps UID -> Operator,
                e.g.
                {
                    "operator1": Operator
                }
                Defaults to None.
            sensors (optional): Sensors in the factory. Note that some of the
                sensors are hardcoded and cannot be provided here,
                e.g. temperature of a machine (MachineTemperatureSensor) and
                factory room temperature (RoomTemperatureSensor).

                Should be a dictionary that maps UID -> Sensor, e.g.
                {
                    "sensor1": Sensor
                }
                Defaults to None.
            collectors (optional): Data collectors in the factory. Should be a
                dictionary that maps UID -> dict,
                e.g.
                {
                    "default-collector": {
                        "name": "Variable collector",
                        "variables": [
                            {
                                "id": factory.datetime,
                                "name": Factory.Datetime,
                                "value_map":
                                    lambda x: x.strftime("%Y-%m-%d %H:%M:%S"),
                                "dtype": "String",
                                "default": "null"
                            },
                            {
                                "id": machine1.state,
                                "name": Machine.State,
                                "value_map":
                                    lambda x: {
                                        "off": 0,
                                        "on": 1,
                                        "production": 2,
                                        "error": 3
                                    }.get(x, 0)
                                "dtype": "Int64",
                                "default": 0
                            }
                        ]
                    }
                }
                Defaults to None.
            exporters (optional): Data exporters in the factory. Should be a
                dictionary that maps UID -> Exporter, e.g.
                {
                    "csv-exporter": CSVExporter
                }
                Defaults to None.
            randomize (optional): Whether to allow randomization of durations,
                failure, etc. or not. Defaults to True.
            monitor (optional): Number of most recent data points to save
                within the Base -object. The higher the number, the more RAM
                it will consume. Set -1 for infinity. Defaults to 100.
            name (optional): Name of the factory. Defaults to "factory"
            uid (optional): Unique ID for the Factory -object. Defaults to
                None.

        Example:

            # Typical workflow
            factory = Factory.from_config("config/factory.yml")
            factory.run(days=7)
            factory.plot()

        Note: Usage through `from_config` -method is recommended!
        """
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
        self.collectors = collectors or {}
        self.exporters = exporters or {}

        # Internal
        self._state = {}
        self.add_sensor(
            # TODO: Define elsewhere
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
        """Return state of all variables."""
        statedict = {
            f"{uid}.{key}": v
            for (dtype, uid, key), (ds, v) in self.data_last.items()
        }

        # Factory time
        if isinstance(self.env, simpy.RealtimeEnvironment):
            now_dt = self.now_dt_real.datetime
        else:
            now_dt = self.now_dt.datetime
        statedict[f"{self.uid}.datetime"] = now_dt

        return statedict

    def get_state(self, collector: dict | None = None):
        """Return state of all variables as defined by the collector."""
        state = self.state
        if collector is None:  # Same keys on every call not guaranteed
            return state

        fieldnames = list(collector["variables"].keys())

        # Map names and apply value map
        statedict = {}
        for field in fieldnames:
            key = collector["variables"][field]["name"]
            value_map = collector["variables"][field]["value_map"]
            default_value = collector["variables"][field].get("default")

            statedict[key] = value_map(state.get(field)) or default_value

        return statedict

    def add_sensor(self, sensor: Sensor):
        """Add sensor into Factory."""
        if sensor.uid not in self.sensors:
            self.sensors[sensor.uid] = sensor
            self.info(f'Added sensor "{sensor.uid}"')
        else:
            self.warning(f"Tried to add existing sensor {sensor.uid}")

    def find_uid(self, uid: str):
        """Find object based on its unique id (uid)."""
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
    def init_env(env: simpy.Environment | simpy.RealtimeEnvironment):
        """Initialize environment object."""
        env.factory_init_event = env.event()
        env.data = defaultdict(lambda: [])
        return env

    @classmethod
    def from_config(cls, path: str, real: bool = False) -> FactoryType:
        """Create Factory object from configuration file (yaml).

        Args:
            path: Filepath into factory configuration YAML-file.
            real: Whether to run simulation in real-time or not. Defaults to
                False.

        Returns:
            Factory object based on given configuration file.
        """
        start = arrow.now("Europe/Helsinki").timestamp()
        if real:
            env = simpy.RealtimeEnvironment(start)
        else:
            env = simpy.Environment(start)

        env = Factory.init_env(env)

        cfg = parse_config(env, path)
        return cls(env, **cfg)

    def run(self, days: int | None = None):
        """Run Factory for given number of days or infinitely.

        Args:
            days (optional): Number of days to run Factory for. If None, then
                run infinitely. Defaults to None.
        """
        until = None if days is None else self.env.now + self.days(days)
        self.env.run(until)

    def plot(self):
        """Plot results for categorical and numerical data of a Factory."""
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
