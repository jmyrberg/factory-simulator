"""Materials."""


import uuid

from src.simulator.base import Base


class Material(Base):
    def __init__(self, env, name="material"):
        super().__init__(env, name=name)


class MaterialBatch(Base):
    def __init__(
        self,
        env,
        material,
        quantity,
        batch_id=None,
        created_ts=None,
        name="material-batch",
    ):
        super().__init__(env, name=name)
        self.material = material
        self.quantity = quantity
        self.created_ts = created_ts or self.now_dt
        if batch_id is None:
            self.batch_id = (
                f'{material.name.replace(" ", "").upper()}'
                f"-{self.created_ts.strftime('%Y%m%d')}"
                f"-{uuid.uuid4().hex[:8].upper()}"
            )
        else:
            self.batch_id = batch_id
