"""Machine programs."""


import simpy
import uuid

from src.base import Base
from src.causes import BaseCause, UnknownCause
from src.issues import LowConsumableLevelIssue
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
        self.batch = {}
        self.events = {
            'program_started': self.env.event(),
            'program_stopped': self.env.event(),
            'program_interrupted': self.env.event(),
            'program_issue': self.env.event()
        }

    def run(self):
        self.emit('program_started')
        self.state = 'on'

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
        for mtype in ['consumables', 'materials']:
            for obj, d in getattr(self.bom, mtype).items():
                container = obj.container
                expected_amount = duration * d['consumption']
                if container.level < expected_amount:
                    self.warning('Will not produce due low consumable level')
                    self.emit('program_issue')
                    self.state = 'issue'
                    raise simpy.Interrupt(LowConsumableLevelIssue(obj))

        # Run or interrupt
        try:
            yield self.env.timeout(duration)
            self.batch['status'] = 'success'
            self.state = 'success'
        except simpy.Interrupt as i:
            self.info(f'Program interrupted: {i.cause}')
            self.emit('program_interrupted')
            if isinstance(i.cause, BaseCause) and not i.cause.force:
                time_left = start_time + duration - self.env.now
                self.debug(
                    f'Waiting for current batch to finish in {time_left:.0f}')
                yield self.env.timeout(time_left)
                self.batch['status'] = 'success'
                self.state = 'success'
            else:
                raise UnknownCause(i.cause)

        # Consume
        end_time = self.env.now
        self.batch['end_time'] = end_time
        time_spent = end_time - start_time
        for mtype in ['consumables', 'materials']:
            for obj, d in getattr(self.bom, mtype).items():
                amount = time_spent * d['consumption']
                self.debug(f'Consuming {amount:.2f} of {obj.name}')
                yield from obj.consume(amount)

        self.state = 'off'
        self.emit('program_stopped')
