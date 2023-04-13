"""Machine programs."""


import simpy

from src.simulator.base import Base


class Consumable(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        name: str = "consumable",
        uid: str | None = None,
    ):
        """Consumable.

        Args:
            env: Simpy environment.
            name (optional): Name of the consumable. Defaults to "consumable".
            uid (optional): Unique ID for the consumable. Defaults to None.
        """
        super().__init__(env, name=name, uid=uid)
