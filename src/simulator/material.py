"""Materials."""


import hashlib
import uuid

from src.simulator.base import Base


class Material(Base):
    def __init__(self, env, name="material", uid=None):
        super().__init__(env, name=name, uid=uid)


class MaterialBatch(Base):
    def __init__(
        self,
        env,
        material,
        quantity,
        quality=None,
        consumption_factor=None,
        batch_id=None,
        created_ts=None,
        name="material-batch",
    ):
        super().__init__(env, name=name)
        self.material = material
        self.quantity = quantity
        self.quality = min(
            1,
            1
            if quality is None
            else self.pnorm(*quality, force_randomize=True),
        )
        self.consumption_factor = max(
            1,
            1
            if consumption_factor is None
            else self.pnorm(*consumption_factor, force_randomize=True),
        )
        self.created_ts = created_ts or self.now_dt
        if batch_id is None:
            self.batch_id = (
                f'{material.name.replace(" ", "").upper()}'
                f"-{self.created_ts.strftime('%Y%m%d')}"
                f"-{uuid.uuid4().hex[:8].upper()}"
            )
        else:
            self.batch_id = batch_id

    @property
    def material_id(self):
        return int(hashlib.sha256(
            self.batch_id.encode('utf-8')).hexdigest(),
            16
        ) % 10 ** 8

    @property
    def effective_quantity(self):
        return self.quantity / self.consumption_factor

    @classmethod
    def from_existing(cls, batch, new_quantity=None):
        new = cls(
            env=batch.env,
            material=batch.env,
            quantity=new_quantity or batch.quantity,
            batch_id=batch.batch_id,
            created_ts=batch.created_ts,
            name=batch.name,
        )
        new.quality = batch.quality
        new.consumption_factor = batch.consumption_factor
        return new
