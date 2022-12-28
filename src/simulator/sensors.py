"""Materials."""


from src.simulator.base import Base
from src.simulator.utils import AttributeMonitor


def get_sensor_by_type(sensor_type):
    sensor_types = {"room-temperature": RoomTemperatureSensor}
    return sensor_types[sensor_type]


class Sensor(Base):

    value = AttributeMonitor()

    def __init__(self, env, interval=60, init_value=None, name="Sensor"):
        super().__init__(env, name=name)
        self.interval = interval
        self.value = init_value

        self.procs = {"run": self.env.process(self._run())}

    def _run(self):
        while True:
            yield self.env.timeout(self.interval)
            self.value = self.get_value()

    def get_value(self):
        raise NotImplementedError('Method "get_value" must be implemented!')


class RoomTemperatureSensor(Sensor):

    value = AttributeMonitor("numerical", name="room_temperature")

    def __init__(self, *args, factory_uid, decimals=2, **kwargs):
        kwargs["name"] = f"RoomTemperatureSensor({factory_uid})"
        super().__init__(*args, **kwargs)
        self.factory_uid = factory_uid
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
        delta_h = self.hourly_delta[self.now_dt.hour]
        noise = self.norm(0, 0.5)
        target = self.base_temp + delta_h + noise

        prev_value = self.value
        if prev_value is not None:
            new_value = 0.5 * prev_value + 0.5 * target
        else:
            new_value = target

        return round(new_value, self.decimals)
