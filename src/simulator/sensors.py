"""Sensors."""


import numpy as np
import simpy

from src.simulator.base import Base
from src.simulator.issues import OverheatIssue
from src.simulator.utils import AttributeMonitor, wait_factory


def get_sensor_by_type(sensor_type):
    """Get sensor based on its type."""
    sensor_types = {"room-temperature": RoomTemperatureSensor}
    return sensor_types[sensor_type]


class Sensor(Base):

    value = AttributeMonitor("numerical")

    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        interval: int = 5,
        init_value: float | int | None = None,
        name: str = "sensor",
        uid: str | None = None,
    ):
        """Sensor that produces or measures data from a process.

        Args:
            env: Simpy environment.
            interval (optional): Update interval of the sensor in simulation
                time units. Defaults to 5.
            init_value (optional): Initial value of the sensor. Defaults to
                None.
            name (optional): Name of the sensor. Defaults to "sensor".
            uid (optional): Unique ID for the operating schedule. Defaults to
                None.
        """
        super().__init__(env, name=name, uid=uid)
        self.interval = interval
        self.value = init_value
        self.env.process(self._init())

    @wait_factory
    def _init(self):
        yield self.wnorm(0)
        if self.uid not in self.env.factory.sensors:
            self.env.factory.add_sensor(self)
        self.procs = {"run": self.env.process(self.run())}

    def run(self):
        while True:
            yield self.wnorm(self.interval)
            self.value = self.get_value()

    def get_value(self):
        raise NotImplementedError('Method "get_value" must be implemented!')


class MachineTemperatureSensor(Sensor):

    value = AttributeMonitor("numerical", name="temperature")

    def __init__(self, env, machine, decimals=2, uid=None, **kwargs):
        """Sensor for machine temperature."""
        kwargs["name"] = f"MachineTemperatureSensor({machine.name})"
        super().__init__(env, uid=uid, **kwargs)
        self.machine = machine
        self.decimals = decimals

        self.change_per_hour = {
            "production": 10,
            "on": 1,
            "idle": -3,
            "off": -3,
            "error": -5,
        }

        self.events = {
            "temperature_changed": self.env.event(),
        }
        self.procs = {
            "temp_monitor": self.env.process(self._temp_monitor_proc()),
        }

    def _temp_monitor_proc(self):
        warned_already = False
        while True:
            yield self.events["temperature_changed"]
            if self.value > 80 and self.machine.state != "error":
                issue = OverheatIssue(self, self.value, 80)
                self.env.process(self.machine._switch_error(issue))
                yield self.machine.events["switched_error"]
                warned_already = False
            elif self.value > 70 and not warned_already:
                self.warning(f"Temperature very high: {self.value}")
                warned_already = True

    def run(self):
        # Start main loop only when factory is accessible
        room_temp_sensor = [
            sensor
            for sensor in self.env.factory.sensors.values()
            if isinstance(sensor, RoomTemperatureSensor)
        ][
            0
        ]  # FIXME: Assume only one sensor per factory now

        update_time = self.env.now
        temp = room_temp_sensor.value
        while True:
            # Wait for state change that affects the temperature
            timeout = self.wnorm(self.interval)
            state_change = self.machine.events["state_change"]
            res = yield timeout | state_change
            if timeout in res:  # From timeout
                state = self.machine.state
            else:
                state = state_change.value  # Machine state changed into

            duration = self.env.now - update_time
            duration_hours = duration / 60 / 60
            update_time = self.env.now

            # Change depends on the duration of the previous state
            # The further away from room temperature, the faster the cooling
            room_temp = room_temp_sensor.value
            if temp is None:
                temp = room_temp if room_temp is not None else 19

            # ~5 degrees in an hour if difference is 100
            delta_room = (room_temp - temp) / 5 * duration_hours

            delta_mode = self.change_per_hour[state] * duration_hours

            # Program and material batch quantity affects temperature
            if state == "production":
                program_temp_factor = self.machine.program.temp_factor
                # Worse effective quality = hotter
                # TODO: Quality should be set before a batch, not after
                if self.machine.program.quality is not None:
                    quality_factor = self.machine.program.quality
                else:
                    quality_factor = 1

                delta_mode *= program_temp_factor / quality_factor

            maybe_new_temp = temp + delta_mode + delta_room
            noise = self.norm(0, duration_hours * 10)
            new_temp = max(room_temp, maybe_new_temp) + noise

            temp = new_temp  # = current temperature

            # Sensor is updated only if update is from timeout
            if timeout in res:
                self.value = round(temp, self.decimals)
                self.emit("temperature_changed", skip_log=True)
                # self.debug(f"Value updated: {self.value:.2f}")


class RoomTemperatureSensor(Sensor):

    value = AttributeMonitor("numerical", name="temperature")

    def __init__(self, env, factory, decimals=2, uid=None, **kwargs):
        """Sensor for factory room temperature."""
        kwargs["name"] = f"RoomTemperatureSensor({factory.name})"
        super().__init__(env, init_value=19, uid=uid, **kwargs)
        self.factory = factory
        self.decimals = decimals

        self.base_temp = 19
        self.hourly_delta = [
            -2.5,
            -2.75,
            -3,
            -2.5,
            -2,
            -1.5,
            -1,
            0,  # 0-7
            1,
            2,
            3,
            3.1,
            3.25,
            3.5,
            3.1,
            2.5,  # 8-15
            2,
            1,
            0,
            -1,
            -1.5,
            -1.75,
            -2,
            -2.25,  # 16-23
        ]

    def get_value(self):
        # Avg. machine temp + hourly delta + noise
        prev_temp = self.value

        machine_temps = []
        for sensor in self.factory.sensors.values():  # Should be up-to-date
            if (
                isinstance(sensor, MachineTemperatureSensor)
                and sensor.value is not None
            ):
                machine_temps.append(sensor.value)

        if len(machine_temps) == 0:
            delta_machine = 0
        else:
            machine_temp = np.mean(machine_temps)
            n_machines = len(machine_temps)
            duration_hours = self.interval / 60 / 60
            delta_temp = machine_temp - prev_temp
            delta_machine = 2 * delta_temp * n_machines * duration_hours

        delta_h = self.hourly_delta[self.now_dt.hour]
        noise = self.norm(0, 0.5)
        target = self.base_temp + delta_machine + delta_h + noise

        temp = 0.25 * prev_temp + 0.75 * target

        return round(temp, self.decimals)
