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
from src.simulator.issues import (
    BaseIssue,
    ContainerMissingIssue,
    LowContainerLevelIssue,
)
from src.simulator.product import ProductBatch
from src.simulator.utils import AttributeMonitor


class Program(Base):
    # TODO: Create a couple of different kinds of programs (Batch/Maintenance)

    state = AttributeMonitor()

    def __init__(
        self,
        uid: str,
        env,
        bom,
        duration_minutes=15,
        temp_factor=1.0,
        name="program",
    ) -> None:
        """Machine program."""
        super().__init__(env, name=name, uid=uid)
        self.uid = uid
        self.bom = bom
        self.duration_minutes = duration_minutes
        self.temp_factor = temp_factor

        # Internal states
        self.state = "off"
        self.batch_id = None
        self.quality = None  # Updated in run
        self.output_factor = None  # Updated in run
        self.consumption = self.with_monitor(
            {},
            post=[
                (obj.uid, lambda x: x[obj.uid] if obj.uid in x else 0)
                for mtype in ["consumables", "materials"]
                for obj, d in getattr(self.bom, mtype).items()
            ],
            name="consumption",
        )
        # TODO: Do all of these default settings more concisely
        for mtype in ["consumables", "materials"]:
            for obj, d in getattr(self.bom, mtype).items():
                self.consumption[obj.uid] = 0
        self.product_quantity = self.with_monitor(
            {},
            post=[
                (obj.uid, lambda x: x[obj.uid] if obj.uid in x else 0)
                for obj, d in self.bom.products.items()
            ],
            name="product_quantity",
        )
        for obj, d in self.bom.products.items():
            self.product_quantity[obj.uid] = 0
        self.latest_batch_id = self.with_monitor(
            {},
            post=[
                (obj.uid, lambda x: x[obj.uid] if obj.uid in x else "null")
                for obj, d in self.bom.materials.items()
            ],
            name="latest_batch_id",
        )
        for obj, d in self.bom.materials.items():
            self.latest_batch_id[obj.uid] = "null"

        self.locked_containers = defaultdict(list)
        self.events = {
            "program_started": self.env.event(),
            "program_stopped": self.env.event(),
            "program_interrupted": self.env.event(),
            "program_issue": self.env.event(),
        }

        for obj, d in self.bom.products.items():
            self.info(
                f"Max. hourly quantity {obj.uid}: "
                f"{60 / self.duration_minutes * d['quantity']:.0f}"
            )

    def get_material_uids(self):
        comps = set()
        for obj, _ in getattr(self.bom, "materials").items():
            comps.add(obj.uid)

        return sorted(list(comps))

    def get_consumable_uids(self):
        comps = set()
        for obj, _ in getattr(self.bom, "consumables").items():
            comps.add(obj.uid)

        return sorted(list(comps))

    def _check_inputs(
        self, machine, expected_duration, lock=True, safety_margin=2.0
    ):
        for mtype in ["consumables", "materials"]:
            for obj, d in getattr(self.bom, mtype).items():
                # Containers exist?
                containers = find_containers_by_type(obj, machine.containers)
                if len(containers) == 0:
                    raise simpy.Interrupt(ContainerMissingIssue(obj))

                # Target quantity exists?
                quantity = expected_duration * d["consumption"] * safety_margin
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

    def _consume_inputs(self, time_spent, machine=None, unlock=True):
        self.debug(f"Consuming inputs for {time_spent=:.2f}")
        output_factor = 1
        qualities = []
        total_quantity = 0
        for mtype in ["consumables", "materials"]:
            for obj, d in getattr(self.bom, mtype).items():
                if obj not in self.locked_containers:
                    raise ValueError(f'Impossible to consume "{obj}"')

                containers, requests = zip(*self.locked_containers[obj])

                base_quantity = time_spent * d["consumption"]

                # TODO: Pct. as param. or sth.
                quantity = self.cnorm(
                    low=0.99 * base_quantity, high=1.01 * base_quantity
                )
                batches, total_effective = get_from_containers(
                    quantity, containers
                )

                # Output is based on the effective quantity
                # Consumables = 1:1
                # Material depends on consumption_factor (effective quantity)
                output_factor *= total_effective / quantity
                # TODO: Save batches + total
                self.debug(f"Consumed {total_effective:.2f} of {obj.uid}")

                # Quality determines output quality - we take the weighted avg.
                # Only material considered for the moment
                # TODO: Same for consumables
                qualities.extend([b.quantity * b.quality for b in batches])
                total_quantity += sum(b.quantity for b in batches)

                # Log consumption
                # Program
                if obj.uid not in self.consumption:
                    self.consumption[obj.uid] = 0
                self.consumption[obj.uid] = (
                    self.consumption[obj.uid] + total_effective
                )

                # Machine
                if machine is not None:
                    if obj.uid not in machine.consumption:
                        machine.consumption[obj.uid] = 0
                    machine.consumption[obj.uid] = (
                        machine.consumption[obj.uid] + total_effective
                    )

                # Log material id
                # Program
                if mtype == "materials":
                    self.latest_batch_id[obj.uid] = batches[-1].batch_id

                    # Machine
                    if machine is not None:
                        machine.latest_batch_id[obj.uid] = batches[-1].batch_id
                        machine.material_id[obj.uid] = batches[-1].material_id

        if unlock:  # Needs to happen after consumption ^
            self._unlock_containers()

        quality = sum(qualities) / total_quantity if total_quantity > 0 else 1

        return output_factor, quality

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

        duration = self.minutes(self.duration_minutes) + self.pnorm(
            self.minutes(0), 1
        )

        # Checks - lock prevents other consumption
        yield from self._check_inputs(machine, duration)

        # Run or interrupt
        # TODO: Run in a while loop with a given resolution
        product_str = ",".join(
            list(map(lambda x: x.uid, self.bom.products.keys()))
        )
        created_ts = self.now_dt.strftime("%Y%m%d%H%M%S")
        self.batch_id = (
            f'{product_str.replace(" ", "").upper()}'
            f'-{machine.uid.replace(" ", "").upper()}'
            f"-{created_ts}"
            f"-{uuid.uuid4().hex[:8].upper()}"
        )
        start_time = self.env.now
        try:
            yield self.wnorm(duration)
            self.state = "success"
        except simpy.Interrupt as i:
            self.info(f"Program interrupted: {i.cause}")
            self.emit("program_interrupted")

            if isinstance(i.cause, BaseCause) and not i.cause.force:
                time_left = start_time + duration - self.env.now
                self.debug(
                    f"Waiting for current batch to finish in {time_left:.0f}"
                )
                yield self.wnorm(time_left)
                self.state = "success"
            elif isinstance(i.cause, BaseCause) and i.cause.force:
                self.debug("Not waiting for current batch to finish")
            elif isinstance(i.cause, BaseIssue):
                self.debug("Not waiting for current batch to finish")
            else:
                raise UnknownCause(i.cause)

        # Consume inputs (should always reach here and run it)
        # Unlock allows others to use the containers again
        end_time = self.env.now
        time_spent = end_time - start_time
        self.output_factor, self.quality = self._consume_inputs(
            time_spent, machine=machine
        )

        for obj, d in self.bom.products.items():
            containers = find_containers_by_type(obj, machine.containers)
            for container in containers:
                base_quantity = d["quantity"]
                # TODO: Percentage as param or sth.
                quantity = self.output_factor * self.cnorm(
                    low=0.99 * base_quantity, high=1.01 * base_quantity
                )
                batch = ProductBatch(
                    env=self.env,
                    product=obj,
                    batch_id=self.batch_id,
                    quantity=max(int(quantity), 1),
                    quality=self.quality,
                    details={"start_time": start_time, "end_time": end_time},
                )
                container.put(batch)

                # Log outputs for this machine
                # TODO: Could be removed and as productcontainer is similar
                if obj.uid not in self.product_quantity:
                    self.product_quantity[obj.uid] = 0
                self.product_quantity[obj.uid] += batch.quantity

        self.state = "off"
        self.emit("program_stopped")
