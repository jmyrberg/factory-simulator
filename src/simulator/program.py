"""Machine programs."""


import uuid
from collections import defaultdict

import simpy

from src.simulator.base import Base
from src.simulator.causes import BaseCause, UnknownCause
from src.simulator.containers import (
    find_containers_by_type,
    get_from_containers,
    quantity_exists_in_containers,
)
from src.simulator.issues import ContainerMissingIssue, LowContainerLevelIssue
from src.simulator.product import ProductBatch
from src.simulator.utils import AttributeMonitor


class Program(Base):
    # TODO: Create a couple of different kinds of programs (Batch/Maintenance)

    state = AttributeMonitor()

    def __init__(self, uid: str, env, bom, name="program") -> None:
        """Machine program."""
        super().__init__(env, name=name)
        self.uid = uid
        self.bom = bom

        # Internal states
        self.state = "off"
        self.batch_id = None
        self.consumption = self.with_monitor(
            {},
            post=[  # TODO: Use UIDs instead of name
                (obj.name, lambda x: x[obj.name] if obj.name in x else 0)
                for mtype in ["consumables", "materials"]
                for obj, d in getattr(self.bom, mtype).items()
            ],
            name="consumption",
        )
        # TODO: Do all of these default settings more concisely
        for mtype in ["consumables", "materials"]:
            for obj, d in getattr(self.bom, mtype).items():
                self.consumption[obj.name] = 0
        self.product_quantity = self.with_monitor(
            {},
            post=[  # TODO: Use UIDs instead of name
                (obj.name, lambda x: x[obj.name] if obj.name in x else 0)
                for obj, d in self.bom.products.items()
            ],
            name="product_quantity",
        )
        for obj, d in self.bom.products.items():
            self.product_quantity[obj.name] = 0
        self.latest_batch_id = self.with_monitor(
            {},
            post=[
                (obj.name, lambda x: x[obj.name] if obj.name in x else "null")
                for obj, d in self.bom.materials.items()
            ],
            name="latest_batch_id",
        )
        for obj, d in self.bom.materials.items():
            self.latest_batch_id[obj.name] = "null"

        self.locked_containers = defaultdict(list)
        self.events = {
            "program_started": self.env.event(),
            "program_stopped": self.env.event(),
            "program_interrupted": self.env.event(),
            "program_issue": self.env.event(),
        }

    def _check_inputs(self, machine, expected_duration, lock=True):
        for mtype in ["consumables", "materials"]:
            for obj, d in getattr(self.bom, mtype).items():
                # Containers exist?
                containers = find_containers_by_type(obj, machine.containers)
                if len(containers) == 0:
                    raise simpy.Interrupt(ContainerMissingIssue(obj))

                # Target quantity exists?
                quantity = expected_duration * d["consumption"]
                if not quantity_exists_in_containers(quantity, containers):
                    self.warning("Will not produce due low container level")
                    self.emit("program_issue")
                    self.state = "issue"
                    self._unlock_containers()
                    raise simpy.Interrupt(LowContainerLevelIssue(containers))

                if lock:
                    for container in containers:
                        self.debug(f'Locking "{container}" for "{self}"...')
                        request = container.lock.request()
                        yield request
                        self.locked_containers[obj].append(
                            (container, request)
                        )
                        self.debug(f'Locked "{container}" for "{self}"')

    def _consume_inputs(self, time_spent, unlock=True):
        self.debug(f"Consuming inputs for {time_spent=:.2f}")
        for mtype in ["consumables", "materials"]:
            for obj, d in getattr(self.bom, mtype).items():
                if obj not in self.locked_containers:
                    raise ValueError(f'Impossible to consume "{obj}"')

                containers, requests = zip(*self.locked_containers[obj])

                quantity = time_spent * d["consumption"]
                batches, total = get_from_containers(quantity, containers)
                # TODO: Save batches + total
                self.debug(f"Consumed {total:.2f} of {obj.name}")

                # Log consumption
                if obj.name not in self.consumption:
                    self.consumption[obj.name] = 0

                self.consumption[obj.name] += total

                # Log material id
                if mtype == "materials":
                    self.latest_batch_id[obj.name] = batches[-1].batch_id

        if unlock:  # Needs to happen after consumption ^
            self._unlock_containers()

    def _unlock_containers(self):
        objs_to_delete = []
        for obj, containers in self.locked_containers.items():
            for container, request in containers:
                container.lock.release(request)
                objs_to_delete.append(obj)
                self.debug(f'Unlocked "{container}" from "{self}"')

        for obj in objs_to_delete:
            del self.locked_containers[obj]

    def run(self, machine):
        self.emit("program_started")
        self.state = "on"

        duration = 60 * 15  # TODO: Sample

        # Checks - lock prevents other consumption
        yield from self._check_inputs(machine, duration)

        # Run or interrupt
        # TODO: Run in a while loop with a given resolution
        self.batch_id = uuid.uuid4().hex
        start_time = self.env.now
        try:
            yield self.env.timeout(duration)
            self.state = "success"
        except simpy.Interrupt as i:
            self.info(f"Program interrupted: {i.cause}")
            self.emit("program_interrupted")

            if isinstance(i.cause, BaseCause) and not i.cause.force:
                time_left = start_time + duration - self.env.now
                self.debug(
                    f"Waiting for current batch to finish in {time_left:.0f}"
                )
                yield self.env.timeout(time_left)
                self.state = "success"
            else:
                raise UnknownCause(i.cause)

        # Consume inputs (should always reach here and run it)
        # Unlock allows others to use the containers again
        end_time = self.env.now
        time_spent = end_time - start_time
        self._consume_inputs(time_spent)

        for obj, d in self.bom.products.items():
            containers = find_containers_by_type(obj, machine.containers)
            for container in containers:
                batch = ProductBatch(
                    env=self.env,
                    product=obj,
                    batch_id=self.batch_id,
                    quantity=d["quantity"],
                    details={"start_time": start_time, "end_time": end_time},
                )
                container.put(batch)

                # Log outputs for this machine
                if obj.name not in self.product_quantity:
                    self.product_quantity[obj.name] = 0
                self.product_quantity[obj.name] += batch.quantity

        self.state = "off"
        self.emit("program_stopped")
