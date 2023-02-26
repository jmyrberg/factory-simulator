"""Container for material and consumables."""


import logging
from typing import List

import numpy as np
import simpy

from src.simulator.base import Base
from src.simulator.material import MaterialBatch
from src.simulator.product import ProductBatch

logger = logging.getLogger(__name__)


class ConsumableContainer(Base):
    def __init__(
        self,
        env,
        consumable,
        capacity=100.0,
        init=None,
        fill_rate=50,
        resolution=60,
        name="consumable-container",
        uid=None,
    ):
        """Container with continuous contents."""
        super().__init__(env, name=name, uid=uid)
        self.consumable = consumable
        self.init = init
        self.fill_rate = fill_rate  # units per hour
        self.resolution = resolution  # update time units

        self.lock = self.with_monitor(simpy.PriorityResource(env), name="lock")
        self.container = self.with_monitor(
            simpy.Container(env=env, capacity=capacity, init=init or capacity),
            name=self.uid,
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

    def put_full(self, pct=1.0):
        yield from self.put(pct * self.free)

    def put(self, quantity: float) -> float:
        """Yields."""
        if quantity > self.free:
            old_quantity = quantity
            quantity = self.free
            self.warning(
                f"Adjusted quantity from {old_quantity} to "
                f"{quantity} to fit the container"
            )

        duration_hours = self.pnorm(quantity / self.fill_rate, 0.01)
        duration = self.hours(duration_hours)
        time_left = duration
        self.debug(
            f"Filling container with {quantity:.2f} in "
            f"{duration_hours:.2f} hours"
        )

        while time_left > 0:  # Fill in batches with given time resolution
            to_wait = min(time_left, self.resolution)
            add_quantity = to_wait / duration * quantity
            yield self.env.timeout(to_wait)
            self.container.put(add_quantity)

            self.debug(
                f"New level after put: "
                f"{self.level:.2f} / {self.capacity:.2f}"
            )

            time_left -= to_wait

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
        resolution=60,
        init=None,
        name="material-container",
        uid=None,
    ):
        """Container with discrete contents."""
        super().__init__(env, name=name, uid=uid)
        self.material = material
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.resolution = resolution
        self.init = init

        # Internal
        self.lock = self.with_monitor(simpy.PriorityResource(env), name="lock")
        self.batches = self.with_monitor(
            [],
            post=[
                ("n_batches", lambda x: len(x)),
                ("quantity", lambda x: sum(b.quantity for b in x)),
                (
                    "effective_quantity",
                    lambda x: sum(b.effective_quantity for b in x),
                ),
                (
                    "last_batch_id",
                    lambda x: x[-1].batch_id if len(x) > 0 else None,
                    "categorical",
                ),
                (
                    "last_batch_quality",
                    lambda x: x[-1].quality if len(x) > 0 else None,
                    "numerical",
                ),
                (
                    "last_batch_consumption_factor",
                    lambda x: x[-1].consumption_factor if len(x) > 0 else None,
                    "numerical",
                ),
            ],
            name="batches",
        )
        if init is None:
            # TODO: From procurement as well
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

    def put_full(self, pct=1.0, quality=None, consumption_factor=None):
        batch = MaterialBatch(
            env=self.env,
            material=self.material,
            quantity=pct * self.free,
            quality=quality,
            consumption_factor=consumption_factor,
        )
        yield from self.put(batch)

    def put(self, batch_or_quantity: MaterialBatch | float) -> MaterialBatch:
        """Yields."""
        # TODO: Lock while filling
        if isinstance(batch_or_quantity, MaterialBatch):
            batch = batch_or_quantity
        else:
            raise TypeError("Input should be of type 'MaterialBatch'")

        if batch.quantity > self.free:
            self.warning(
                f"Adjusting batch quantity from {batch.quantity} to "
                f"{self.free} to fit the container"
            )
            quantity = self.free
        else:
            quantity = batch.quantity

        if quantity > 0:
            # Init with zero quantity and little by little
            batch.quantity = 0
            self.batches.insert(0, batch)

            duration_hours = self.pnorm(quantity / self.fill_rate, 0.01)
            duration = self.hours(duration_hours)
            time_left = duration
            self.debug(
                f"Filling container with {quantity:.2f} in "
                f"{duration_hours:.2f} hours"
            )
            while time_left > 0:  # Fill in batches with given time resolution
                to_wait = min(time_left, self.resolution)
                add_quantity = to_wait / duration * quantity
                yield self.env.timeout(to_wait)
                self.batches[0].quantity += add_quantity

                self.debug(
                    f"New level after put: "
                    f"{self.level:.2f} / {self.capacity:.2f}"
                )

                time_left -= to_wait

            assert np.isclose(self.batches[0].quantity, quantity)
            self.batches[0].quantity = quantity
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
            batch = self.batches[-1]

            missing_quantity = quantity - fetch_quantity
            new_quantity = fetch_quantity + batch.quantity

            if new_quantity > quantity:  # Need to split the batch
                # Remove from batch
                batch.quantity -= missing_quantity
                self.batches[-1] = batch  # Log change

                # ...and add to fetch batch
                fetch_quantity += missing_quantity
                fetch_batch = MaterialBatch.from_existing(
                    batch, missing_quantity
                )
                fetch_batches.append(fetch_batch)
            else:  # Last batch
                fetch_quantity += batch.quantity
                fetch_batches.append(batch)
                self.batches.pop()

            if fetch_quantity == quantity:
                break

            if fetch_quantity > quantity:
                raise ValueError("Should not happen")

        self.debug(
            f"New level after get: " f"{self.level:.2f} / {self.capacity:.2f}"
        )

        return fetch_batches


class ProductContainer(Base):
    def __init__(self, env, product, name="product-container", uid=None):
        """Container with discrete contents."""
        super().__init__(env, name=name, uid=uid)
        self.product = product
        self.batches = self.with_monitor(
            [],
            post=[
                ("n_batches", lambda x: len(x)),
                ("quantity", lambda x: sum(b.quantity for b in x)),
                (
                    "failed_quantity",
                    lambda x: sum(b.failed_quantity for b in x),
                ),
                (
                    "success_quantity",
                    lambda x: sum(b.success_quantity for b in x),
                ),
                # (
                #     "last_batch_id",
                #     lambda x: x[-1].batch_id if len(x) > 0 else None,
                #     "categorical",
                # ),
                (
                    "last_batch_quality",
                    lambda x: x[-1].quality if len(x) > 0 else None,
                    "numerical",
                ),
                (
                    "average_quality",
                    lambda x: np.mean([b.quality for b in x])
                    if len(x) > 0
                    else None,
                    "numerical",
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
                total += sum(b.effective_quantity for b in got)
            else:  # Consumable
                total += got

            left = quantity - total
            if left == 0:
                break

        return batches, total
    else:
        # TODO: Take evenly from all containers etc.
        raise ValueError(f'Unknown strategy "{strategy}"')


def put_into_material_containers(batches, containers, strategy="first"):
    batches_put = []
    total_put = 0
    total_to_put = sum(batch.quantity for batch in batches)
    if strategy == "first":
        for batch in batches:
            for container in containers:
                if container.free == 0:
                    continue

                put_batch = yield from container.put(batch)
                batches_put.append(put_batch)
                total_put += put_batch.quantity

                if put_batch.quantity == batch.quantity:  # All fit
                    break
                else:  # Remainders
                    batch.quantity -= put_batch.quantity

        if total_put < total_to_put:
            logger.warning(
                "Could not fit everything into material containers "
                f"({total_put} < {total_to_put})"
            )

    return batches_put, total_put


def put_into_consumable_containers(quantity, containers, strategy="first"):
    total_put = 0
    total_to_put = quantity
    if strategy == "first":
        for container in containers:
            if container.free == 0:
                continue

            put_quantity = yield from container.put(quantity)
            total_put += put_quantity

            if total_put == total_to_put:
                break

    if total_put < total_to_put:
        logger.warning(
            "Could not fit everything into consumable containers "
            f"({total_put} < {total_to_put})"
        )

    return total_put


def find_containers_by_type(content, containers, raising=True):
    filtered_containers = []
    for container in containers:
        if (
            isinstance(container, MaterialContainer)
            and container.material == content
        ):
            filtered_containers.append(container)
        elif (
            isinstance(container, ConsumableContainer)
            and container.consumable == content
        ):
            filtered_containers.append(container)
        elif (
            isinstance(container, ProductContainer)
            and container.product == content
        ):
            filtered_containers.append(container)

    if raising and len(filtered_containers) == 0:
        raise ValueError(f'No containers found for "{content}"')

    return filtered_containers
