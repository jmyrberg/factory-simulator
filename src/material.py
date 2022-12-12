"""Materials."""


import uuid

from src.base import Base


class Material(Base):

    def __init__(self, env, name='material'):
        super().__init__(env, name=name)


class MaterialBatch(Base):

    def __init__(self, env, material, quantity, material_id=None,
                 name='material-batch'):
        super().__init__(env, name=name)
        self.material = material
        self.quantity = quantity
        if material_id is None:
            self.material_id = (
                f'{material.name.replace(" ", "").upper()}'
                f'{uuid.uuid4().hex[:8].upper()}')
        else:
            self.material_id = material_id
