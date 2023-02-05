"""Machine programs."""


from typing import Any, Dict

from src.simulator.base import Base


class Product(Base):
    def __init__(self, env, name="product", uid=None):
        """Machine program."""
        super().__init__(env, name=name, uid=uid)
        self.name = name


class ProductBatch(Base):
    def __init__(
        self,
        env,
        product: Product,
        batch_id: str,
        quantity: int,
        quality: float = 1.0,
        details: Dict[str, Any] | None = None,
        name="product-batch",
    ):
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
