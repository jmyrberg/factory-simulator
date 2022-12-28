"""Container for material and consumables."""


import logging
from typing import List

import simpy

from src.simulator.base import Base
from src.simulator.material import MaterialBatch
from src.simulator.product import ProductBatch
from src.simulator.utils import AttributeMonitor, MonitoredList

logger = logging.getLogger(__name__)


class ConsumableContainer(Base):
    def __init__(
        self,
        env,
        consumable,
        capacity=100.0,
        init=None,
        fill_rate=50,
        name="consumable-container",
    ):
        """Container with continuous contents."""
        super().__init__(env, name=name)
        self.consumable = consumable
        self.init = init
        self.fill_rate = fill_rate  # units per hour

        self.lock = self.with_monitor(simpy.PriorityResource(env), name="lock")
        self.container = self.with_monitor(
            simpy.Container(env=env, capacity=capacity, init=init or capacity),
            name=name,
        )

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

    def put(self, quantity: float) -> float:
        """Yields."""
        if quantity > self.free:
            old_quantity = quantity
            quantity = self.free
            self.warning(
                f"Adjusted quantity from {old_quantity} to "
                f"{quantity} to fit the container"
            )

        duration_hours = quantity / self.fill_rate

        # TODO: Fill in discrete timepoints
        self.debug(
            "Filling container with {quantity:.2f} in "
            f"{duration_hours:.2f} hours"
        )
        yield self.env.timeout(self.hours(duration_hours))
        self.container.put(quantity)

        self.debug(
            f"New level after put: " f"{self.level:.2f} / {self.capacity:.2f}"
        )
        return quantity

    def get(self, quantity: float) -> float:
        """Returns."""
        if quantity > self.level:
            raise ValueError(f"{quantity=} > {self.level=}")

        self.container.get(quantity)

        self.debug(
            f"New level after get: " f"{self.level:.2f} / {self.capacity:.2f}"
        )
        return quantity


class MaterialContainer(Base):
    def __init__(
        self,
        env,
        material,
        capacity=100.0,
        fill_rate=50,
        init=None,
        name="material-container",
    ):
        """Container with discrete contents."""
        super().__init__(env, name=name)
        self.material = material
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.init = init

        # Internal
        self.lock = self.with_monitor(simpy.PriorityResource(env), name="lock")
        self.batches = self.with_monitor(
            MonitoredList(),
            post=[
                ("n_batches", lambda x: len(x)),
                ("quantity", lambda x: sum(b.quantity for b in x)),
                (
                    "last_material_id",
                    lambda x: x[-1].material_id if len(x) > 0 else None,
                    "categorical",
                ),
            ],
            name="batches",
        )
        if init is None:
            batch = MaterialBatch(
                env, material, quantity=capacity, name="initial-material-batch"
            )
            self.batches.append(batch)

    @property
    def free(self):
        return self.capacity - self.level

    @property
    def level(self):
        return sum(b.quantity for b in self.batches)

    def put_full(self):
        yield from self.put(self.free)

    def put(self, batch_or_quantity: MaterialBatch | float) -> MaterialBatch:
        """Yields."""
        if isinstance(batch_or_quantity, MaterialBatch):
            batch = batch_or_quantity
        else:
            batch = MaterialBatch(
                env=self.env,
                material=self.material,
                quantity=batch_or_quantity,
            )

        if batch.quantity > self.free:
            batch.quantity = self.free
            self.warning(
                f"Adjusted batch quantity from {batch.quantity} to "
                f"{batch.quantity} to fit the container"
            )

        if batch.quantity > 0:
            duration_hours = batch.quantity / self.fill_rate
            # TODO: Fill in discrete timepoints
            self.debug(
                "Filling container with {quantity:.2f} in "
                f"{duration_hours:.2f} hours"
            )
            yield self.env.timeout(self.hours(duration_hours))

            self.batches.insert(0, batch)
        else:
            self.warning("Batch quantity 0, wont fit into container")

        self.debug(
            f"New level after put: " f"{self.level:.2f} / {self.capacity:.2f}"
        )

        return batch

    def get(self, quantity: float) -> List[MaterialBatch]:
        """Returns."""
        if quantity > self.level:
            raise ValueError(f"{quantity=} > {self.level=}")

        fetch_batches = []
        fetch_quantity = 0
        while len(self.batches) > 0:
            # Take one batch at a time
            batch = self.batches.pop()
            self.batches = self.batches  # Log

            missing_quantity = quantity - fetch_quantity
            new_quantity = fetch_quantity + batch.quantity

            if new_quantity > quantity:  # Need to split the batch
                # Remove from batch
                batch.quantity -= missing_quantity
                self.batches.append(batch)
                self.batches = self.batches  # Log

                # ...and add to fetch batch
                fetch_quantity += missing_quantity
                fetch_batch = MaterialBatch(
                    env=batch.env,
                    material=batch.material,
                    quantity=missing_quantity,
                    material_id=batch.material_id,
                    name=batch.name,
                )
                fetch_batches.append(fetch_batch)
            else:  # Last batch
                fetch_quantity += batch.quantity
                fetch_batches.append(batch)

            if fetch_quantity == quantity:
                break

            if fetch_quantity > quantity:
                raise ValueError("Should not happen")

        self.debug(
            f"New level after get: " f"{self.level:.2f} / {self.capacity:.2f}"
        )

        return fetch_batches


class ProductContainer(Base):
    def __init__(self, env, product, name="product-container"):
        """Container with discrete contents."""
        super().__init__(env, name=name)
        self.product = product
        self.batches = self.with_monitor(
            MonitoredList(),
            post=[
                ("n_batches", lambda x: len(x)),
                ("quantity", lambda x: sum(b.quantity for b in x)),
                (
                    "last_batch_id",
                    lambda x: x[-1].batch_id if len(x) > 0 else None,
                    "categorical",
                ),
            ],
            name="batches",
        )

    @property
    def level(self):
        if len(self.batches) > 0:
            return sum(b.quantity for b in self.batches)
        else:
            return 0

    def put(self, batch: ProductBatch):
        self.batches.append(batch)
        self.debug(f'Added batch "{batch}" to {self}')

    def get(self, quantity: float) -> List[ProductBatch]:
        if quantity > self.level:
            raise ValueError(f"{quantity=} > {self.level=}")

        fetch_batches = []
        fetch_quantity = 0
        while len(self.batches) > 0:
            # Take one batch at a time
            batch = self.batches.pop()
            self.batches = self.batches  # Log

            missing_quantity = quantity - fetch_quantity
            new_quantity = fetch_quantity + batch.quantity

            if new_quantity > quantity:  # Need to split the batch
                # Remove from batch
                batch.quantity -= missing_quantity
                self.batches.append(batch)
                self.batches = self.batches  # Log

                # ...and add to fetch batch
                fetch_quantity += missing_quantity
                fetch_batch = ProductBatch(
                    env=batch.env,
                    batch_id=batch.batch_id,
                    product=batch.product,
                    quantity=missing_quantity,
                    name=batch.name,
                )
                fetch_batches.append(fetch_batch)
            else:  # Last batch
                fetch_quantity += batch.quantity
                fetch_batches.append(batch)

            if fetch_quantity == quantity:
                break

            if fetch_quantity > quantity:
                raise ValueError("Should not happen")

        self._level = self.level
        self.debug(
            f"New level after get: " f"{self.level:.2f} / {self.capacity:.2f}"
        )

        return fetch_batches


def quantity_exists_in_containers(quantity, containers):
    """Checks if the quantity exists in the given containers."""
    container_quantity = sum(c.level for c in containers)
    if container_quantity < quantity:
        logger.debug(f"{container_quantity=:.2f} < {quantity=:.2f}")

    return container_quantity >= quantity


def get_from_containers(quantity, containers, strategy="first"):
    """Get quantity from a number of containers.

    Note: No yields should be used here.
    """
    logger.debug(f"Trying to get {quantity:.2f} from the containers")
    if not quantity_exists_in_containers(quantity, containers):
        raise ValueError("Quantity does not exist in containers")

    left = quantity
    batches = []
    total = 0
    if strategy == "first":
        for container in containers:
            to_get = min(container.level, left)
            got = container.get(to_get)

            if isinstance(got, list):  # Material
                batches.extend(got)
                total += sum(b.quantity for b in got)
            else:  # Consumable
                total += got

            left = quantity - total
            if left == 0:
                break
        return batches, total
    else:
        # TODO: Take evenly from all containers etc.
        raise ValueError(f'Unknown strategy "{strategy}"')
