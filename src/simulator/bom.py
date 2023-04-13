"""Bill of materials."""


from typing import Dict

import simpy

from src.simulator.base import Base
from src.simulator.consumable import Consumable
from src.simulator.material import Material
from src.simulator.product import Product


class BOM(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        materials: Dict[Material, dict] | None = None,
        consumables: Dict[Consumable, dict] | None = None,
        products: Dict[Product, dict] | None = None,
        name: str = "bill-of-material",
        uid: str | None = None,
    ):
        """Bill of material maps materials and consumables into products.

        Args:
            env: Simpy environment.
            materials (optional): Dictionary that maps Material object into
                its' properties, e.g.
                {
                    Material: {"consumption": 8}
                }
                defines the consumption of each material for one unit of BOM.
                Defaults to None.
            consumables (optional): Dictionary that maps Consumable object into
                its' properties, e.g.
                {
                    Consumable: {"consumption": 5}
                }
                defines the consumption of each consumable for one unit of BOM.
                Defaults to None.
            products (optional): Dictionary that maps Product object into
                its' properties, e.g.
                {
                    Product: {"quantity": 10}
                }
                defines the quantity of each product produced for one unit of
                BOM. Defaults to None.
            name (optional): Name of the bill of material. Defaults to
                "bill-of-material".
            uid (optional): Unique ID for the bill of material. Defaults to
                None.
        """
        super().__init__(env, name=name, uid=uid)
        self.materials = materials or {}
        self.consumables = consumables or {}
        self.products = products or {}
