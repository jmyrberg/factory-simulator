"""Materials."""


from src.base import Base


class Material(Base):

    def __init__(self, env, name='material'):
        super().__init__(env, name=name)
