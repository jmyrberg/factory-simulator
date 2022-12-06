"""Container for material and consumables."""


import logging

from copy import deepcopy

import simpy
import uuid

from src.base import Base
from src.utils import with_resource_monitor, Monitor


logger = logging.getLogger(__name__)


class ConsumableContainer(Base):

    def __init__(self, env, consumable, capacity=100.0, init=None,
                 name='consumable-container'):
        super().__init__(env, name=name)
        self.consumable = consumable
        self.lock = simpy.PriorityResource(env)
        self.container = with_resource_monitor(simpy.Container(
            env=env,
            capacity=capacity,
            init=init or capacity
        ), 'container', self)

    @property
    def free(self):
        return self.capacity - self.level

    @property
    def capacity(self):
        return self.container.capacity

    @property
    def level(self):
        return self.container.level

    def put_full(self):
        yield from self.put(self.free)

    def put(self, quantity):
        quantity = self.free if quantity > self.free else quantity
        pct_fill = quantity / self.capacity
        yield self.env.timeout(self.hours(2 * pct_fill))
        yield self.container.put(quantity)
        self.log(f'Filled {quantity:.2f} / {self.capacity:.2f}')
        return quantity

    def get(self, quantity):
        self.container.get(quantity)
        self.log(f'Container level: {self.level:.2f}')
        return quantity


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


class MaterialContainer(Base):

    latest_material_id = Monitor()
    _level = Monitor('numerical')
    batches = Monitor('numerical', lambda x: len(x))

    def __init__(self, env, material, capacity=100.0, init=None,
                 name='material-container'):
        super().__init__(env, name=name)
        self.material = material
        self.batches = []
        self.capacity = capacity

        self.lock = simpy.PriorityResource(env)
        self.latest_material_id = None

        if init is None:
            batch = MaterialBatch(env, material, quantity=capacity,
                                  name='initial-material-batch')
            self.batches.append(batch)

        self._level = self.level

    @property
    def free(self):
        return self.capacity - self.level

    @property
    def level(self):
        return sum(b.quantity for b in self.batches)

    def put_full(self):
        yield from self.put(self.free)

    def put(self, batch_or_quantity):
        if isinstance(batch_or_quantity, MaterialBatch):
            batch = batch_or_quantity
        else:
            batch = MaterialBatch(self.env, self.material, batch_or_quantity)

        if batch.quantity > self.free:
            batch.quantity = self.free
            self.warning(f'Adjusted batch quantity from {batch.quantity} to '
                         f'{batch.quantity} to fit the container')

        if batch.quantity > 0:
            pct_fill = batch.quantity / self.capacity
            yield self.env.timeout(self.hours(2 * pct_fill))
            self.batches.insert(0, batch)
            self.batches = self.batches  # Log
        else:
            self.warning('Batch quantity 0, wont fit into container')

        self._level = self.level

    def get(self, quantity):
        if quantity > self.level:
            raise ValueError(f'{quantity=} > {self.level=}')

        fetch_batches = []
        fetch_quantity = 0
        while len(self.batches) > 0:
            batch = self.batches.pop()
            self.batches = self.batches  # Log
            missing_quantity = quantity - fetch_quantity
            new_quantity = fetch_quantity + batch.quantity
            if new_quantity > quantity:
                # Remove from batch
                batch.quantity -= missing_quantity
                self.debug(f'Removed {missing_quantity:.2f} from batch')
                self.batches.append(batch)
                self.batches = self.batches  # Log

                # ...and add to fetch
                fetch_quantity += missing_quantity
                fetch_batch = MaterialBatch(
                    env=batch.env,
                    material=batch.material,
                    quantity=missing_quantity,
                    material_id=batch.material_id,
                    name=batch.name
                )
                fetch_batches.append(fetch_batch)
                self.latest_material_id = fetch_batch.material_id

                # Consume time
                pct_fill = missing_quantity / self.capacity
                # yield self.env.timeout(self.hours(1 * pct_fill))
            else:
                fetch_quantity += batch.quantity
                fetch_batches.append(batch)
                self.latest_material_id = batch.material_id

                # Consume time
                pct_fill = missing_quantity / self.capacity
                # yield self.env.timeout(self.hours(1 * pct_fill))

            if fetch_quantity == quantity:
                break

            if fetch_quantity > quantity:
                raise ValueError('Should not happen')

        self.log(f'Material container level: {self.level:.2f}')
        self._level = self.level
        return fetch_batches


def quantity_exists_in_containers(quantity, containers):
    container_quantity = sum(c.level for c in containers)
    if container_quantity < quantity:
        logger.debug(f'{container_quantity=:.2f} < {quantity=:.2f}')

    return container_quantity >= quantity


def get_from_containers(quantity, containers, strategy='first'):
    """Get quantity from containers.

    Note: No yields should be used here.
    """
    logger.debug(f'Trying to get {quantity:.2f} from the containers')
    if not quantity_exists_in_containers(quantity, containers):
        raise ValueError('Quantity does not exist in containers')

    left = quantity
    batches = []
    total = 0
    if strategy == 'first':
        for container in containers:
            to_get = min(container.level, left)
            got = container.get(to_get)
            if isinstance(got, list):  # Material
                batches.append(got)
                total += sum(b.quantity for b in got)
            else:
                total += got

            left = quantity - total
            if left == 0:
                break
        return batches, total
    else:
        # TODO: Take evenly from all containers etc.
        raise ValueError(f'Unknown strategy "{strategy}"')
