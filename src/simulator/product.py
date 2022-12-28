"""Machine programs."""


from typing import Any, Dict

from src.simulator.base import Base


class Product(Base):
    def __init__(self, env, name="product"):
        """Machine program."""
        super().__init__(env, name=name)
        self.name = name


class ProductBatch(Base):
    def __init__(
        self,
        env,
        product: Product,
        batch_id: str,
        quantity: float,
        details: Dict[str, Any] | None,
        name="material-batch",
    ):
        super().__init__(env, name=name)
        self.product = product
        self.batch_id = batch_id
        self.quantity = quantity
        self.details = details or {}
