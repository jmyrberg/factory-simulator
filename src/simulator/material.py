"""Materials."""


import hashlib
import uuid
from datetime import datetime
from typing import Tuple

import simpy

from src.simulator.base import Base


class Material(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        name: str = "material",
        uid: str | None = None,
    ):
        """Material.

        Args:
            env: Simpy environment.
            name (optional): Name of the material. Defaults to "material".
            uid (optional): Unique ID for the material. Defaults to None.
        """
        super().__init__(env, name=name, uid=uid)


class MaterialBatch(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        material: Material,
        quantity: float,
        quality: Tuple[float, float] | None = None,
        consumption_factor: Tuple[float, float] | None = None,
        batch_id: str | None = None,
        created_ts: datetime | None = None,
        name: str = "material-batch",
    ):
        """Material batch.

        Args:
            env: Simpy environment.
            material (optional): Material of the batch.
            quantity (optional): Quantity of material.
            quality (optional): Quality of material between 0 and 1, where 0
                is the worst possible quality and 1 is the best. Given as
                normal distribution parameters (mu, std). Example value:
                (1, 0.01). Defaults to None, which corresponds to guaranteed
                quality of 1.
            consumption_factor (optional): How much needs to be consumed in
                order to achieve one unit of standardized quality. If 1, then
                effective quantity = quantity, else it's greater and means that
                to achieve one unit of standardized quality, one needs to
                consume `consumption_factor` of quantity. Example value:
                (1, 0.01). Defaults to None, which corresponds to guaranteed
                consumption factor of 1.
            batch_id (optional): Unique identifier of the batch. Defaults to
                None, which corresponds to random hex combined with creation
                timestamp.
            created_ts (optional): Timestamp of batch creation. Defaults to
                None, which corresponds to now.
            name (optional): Name of the material batch. Defaults to
                "material-batch".
        """
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
        return (
            int(hashlib.sha256(self.batch_id.encode("utf-8")).hexdigest(), 16)
            % 10**8
        )

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
