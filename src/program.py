"""Machine programs."""


import simpy
import uuid

from src.base import Base
from src.causes import BaseCause, UnknownCause
from src.issues import LowConsumableLevelIssue


class Program(Base):

    def __init__(self, env, bom):
        """Machine program."""
        super().__init__(env, name='Program')
        self.bom = bom
        self.batch = {}

    def run(self):
        self.debug(f'Starting program {self.name}')
        start_time = self.env.now
        duration = 60 * 15  # TODO: Sample
        self.batch = {
            'id': uuid.uuid4().hex,
            'start_time': start_time,
            'end_time': None,
            'status': 'ongoing'
            # TODO: Quality etc. stats
        }

        # Checks
        for name, d in self.bom.items():
            container = d['consumable'].container
            expected_amount = duration * d['rate']
            if container.level < expected_amount:
                self.warning('Will not produce due low consumable level')
                raise simpy.Interrupt(LowConsumableLevelIssue(d['consumable']))

        # Run or interrupt
        # TODO: What if we don't have enough in tank to consume?
        try:
            yield self.env.timeout(duration)
            self.batch['status'] = 'success'
        except simpy.Interrupt as i:
            self.warning(f'Program interrupted: {i}')
            if isinstance(i.cause, BaseCause) and not i.cause.force:
                time_left = start_time + duration - self.env.now
                self.debug(
                        f'Waiting for current batch to finish in {time_left}')
                yield self.env.timeout(time_left)
                self.batch['status'] = 'success'
            else:
                raise UnknownCause(i.cause)

        # Consume
        end_time = self.env.now
        self.batch['end_time'] = end_time
        time_spent = end_time - start_time
        self.debug(f'Time spent on batch: {time_spent}')
        for name, d in self.bom.items():
            amount = time_spent * d['rate']
            self.debug(f'Consuming {amount:.2f} of {name}')
            yield from d['consumable'].consume(amount)

        self.info('Batch done!')
