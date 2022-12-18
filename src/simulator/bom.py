"""Machine bill of materials."""


from src.simulator.base import Base


class BOM(Base):

    def __init__(self, env, materials=None, consumables=None, products=None,
                 name='bill-of-material'):
        super().__init__(env, name=name)
        self.materials = materials or {}
        self.consumables = consumables or {}
        self.products = products or {}
