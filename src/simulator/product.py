"""Product and product batch."""


from typing import Any, Dict

import simpy

from src.simulator.base import Base


class Product(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        name: str = "product",
        uid: str | None = None,
    ):
        """Product.

        Args:
            env: Simpy environment.
            name (optional): Name of the product. Defaults to "product".
            uid (optional): Unique ID for the material. Defaults to None.
        """
        super().__init__(env, name=name, uid=uid)
        self.name = name


class ProductBatch(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        product: Product,
        batch_id: str,
        quantity: int,
        quality: float = 1.0,
        details: Dict[str, Any] | None = None,
        name="product-batch",
    ):
        """Product batch.

        Args:
            env: Simpy environment.
            product: Prouct of the batch.
            batch_id: Unique identifier of the batch.
            quantity: Quantity of product as an integer.
            quality: Quality of product between 0 and 1, where 0
                is the worst possible quality and 1 is the best. Quality
                determines the portion of batch items that are failed.
                Defaults to 1.
            details (optional): Dictionary of additional information related
                to the batch.
            name (optional): Name of the material batch. Defaults to
                "product-batch".
        """
        super().__init__(env, name=name)
        self.product = product
        self.batch_id = batch_id
        self.quantity = quantity
        self.quality = quality
        self.details = details or {}

    @property
    def failed_quantity(self):
        return int((1 - self.quality) * self.quantity)

    @property
    def success_quantity(self):
        return self.quantity - self.failed_quantity
