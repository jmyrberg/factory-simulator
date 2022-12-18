"""Machine programs."""


from src.simulator.base import Base


class Consumable(Base):

    def __init__(self, env, name='consumable'):
        """Machine program."""
        super().__init__(env, name=name)
