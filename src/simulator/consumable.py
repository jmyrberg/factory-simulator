"""Machine programs."""


from src.simulator.base import Base


class Consumable(Base):
    def __init__(self, env, name="consumable", uid=None):
        """Machine program."""
        super().__init__(env, name=name, uid=uid)
