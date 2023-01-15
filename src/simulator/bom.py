"""Machine bill of materials."""


from src.simulator.base import Base


class BOM(Base):
    def __init__(
        self,
        env,
        materials=None,
        consumables=None,
        products=None,
        name="bill-of-material",
        uid=None,
    ):
        super().__init__(env, name=name, uid=uid)
        self.materials = materials or {}
        self.consumables = consumables or {}
        self.products = products or {}
