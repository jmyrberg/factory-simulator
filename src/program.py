"""Machine programs."""


from collections import defaultdict

import simpy
import uuid

from src.base import Base
from src.causes import BaseCause, UnknownCause
from src.containers import get_from_containers, quantity_exists_in_containers,\
    MaterialContainer, ConsumableContainer
from src.issues import LowContainerLevelIssue, ContainerMissingIssue
from src.utils import Monitor


class Program(Base):
    # TODO: Create a couple of different kinds of programs (Batch/Maintenance)

    state = Monitor()

    def __init__(self, uid, env, bom, name='program'):
        """Machine program."""
        super().__init__(env, name=name)
        self.uid = uid
        self.state = 'off'
        self.bom = bom

        self.locked_containers = defaultdict(list)
        self.batch = {}
        self.events = {
            'program_started': self.env.event(),
            'program_stopped': self.env.event(),
            'program_interrupted': self.env.event(),
            'program_issue': self.env.event()
        }

    def _check_inputs(self, machine, expected_duration, lock=True):
        for mtype in ['consumables', 'materials']:
            for obj, d in getattr(self.bom, mtype).items():
                # Containers exist?
                containers = machine.find_containers(obj)
                if len(containers) == 0:
                    raise simpy.Interrupt(ContainerMissingIssue(obj))

                # Target quantity exists?
                quantity = expected_duration * d['consumption']
                if not quantity_exists_in_containers(quantity, containers):
                    self.warning('Will not produce due low container level')
                    self.emit('program_issue')
                    self.state = 'issue'
                    self._unlock_containers()
                    raise simpy.Interrupt(LowContainerLevelIssue(containers))

                if lock:
                    for container in containers:
                        self.debug(f'Locking "{container}" for "{self}"...')
                        request = container.lock.request()
                        yield request
                        self.locked_containers[obj].append(
                            (container, request))
                        self.debug(f'Locked "{container}" for "{self}"')

    def _consume_inputs(self, time_spent, unlock=True):
        self.debug(f'Consuming inputs for {time_spent=:.2f}')
        for mtype in ['consumables', 'materials']:
            for obj, d in getattr(self.bom, mtype).items():
                if obj not in self.locked_containers:
                    raise ValueError(f'Impossible to consume "{obj}"')

                containers, requests = zip(*self.locked_containers[obj])

                quantity = time_spent * d['consumption']
                batches, total = get_from_containers(quantity, containers)
                # TODO: Save batches + total
                self.debug(f'Consumed {total:.2f} of {obj.name}')

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
        self.emit('program_started')
        self.state = 'on'

        duration = 60 * 15  # TODO: Sample

        # Checks - lock prevents other consumption
        yield from self._check_inputs(machine, duration)

        # Run or interrupt
        start_time = self.env.now
        try:
            yield self.env.timeout(duration)
            self.state = 'success'
        except simpy.Interrupt as i:
            self.info(f'Program interrupted: {i.cause}')
            self.emit('program_interrupted')

            if isinstance(i.cause, BaseCause) and not i.cause.force:
                time_left = start_time + duration - self.env.now
                self.debug(
                    f'Waiting for current batch to finish in {time_left:.0f}')
                yield self.env.timeout(time_left)
                self.state = 'success'
            else:
                raise UnknownCause(i.cause)

        # Consume inputs (should always reach here and run it)
        # Unlock allows others to use the containers again
        end_time = self.env.now
        time_spent = end_time - start_time
        try:
            self._consume_inputs(time_spent)
        except simpy.Interrupt as i:
            self.error('SHOULD NOT HAPPEN!')
            raise i

        self.state = 'off'
        self.emit('program_stopped')
