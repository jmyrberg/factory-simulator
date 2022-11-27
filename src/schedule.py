"""Schedules."""


from datetime import datetime, timedelta

import arrow
import simpy

from croniter import croniter

from src.base import Base
from src.utils import Monitor


class Block(Base):

    is_active = Monitor()
    program = Monitor()

    def __init__(self, env, program=None, name=None):
        super().__init__(env, name=name or 'Block')
        self.program = program
        self.is_active = False
        self.deleted = False
        self.events = {
            # Block related
            'start': self.env.event(),
            'started': self.env.event(),
            'stop': self.env.event(),
            'stopped': self.env.event()
        }
        self.procs = {
            'run': self.env.process(self._run())
        }

    def delete(self):
        self.procs['run'].interrupt('Deleted')
        self.deleted = True

    def start(self):
        """Activate block from outside."""
        if self.is_active:
            self.warning('Tried to start an active block')
        else:
            self.emit('start')

    def stop(self):
        """Deactivate block from outside."""
        if self.is_active:
            self.emit('stop')
        else:
            self.warning('Tried to stop an active block')

    def assign_schedule(self, schedule):
        self.schedule = schedule

    def assign_program(self, program):
        self.program = program

    def _run(self):
        while True:
            try:
                # Wait for start
                yield self.events['start']

                # Start
                self.emit('started')
                self.is_active = True

                # Trigger block activation in schedule
                if self.schedule:
                    self.schedule.emit('block_started', self)
                else:
                    self.warning('No schedule to trigger')

                # Stop
                yield self.events['stop']
                self.is_active = False

                # Trigger block stop in schedule
                self.schedule.emit('block_finished', self)
            except simpy.Interrupt:  # = delete
                self.is_active = False
                # Trigger block stop in schedule
                self.schedule.emit('block_deleted', self)
                break


class CronBlock(Block):

    def __init__(self, env, start_expr, duration_hours, program=None):
        name = f'CronBlock({start_expr}, {program})'
        super().__init__(env, program, name=name)
        self.start_expr = start_expr
        self.duration_hours = duration_hours
        self.next_start_dt = None
        self.next_end_dt = None

        self.env.process(self.start_cond())

    def __repr__(self):
        return self.name

    def start_cond(self):
        cron_iter = croniter(self.start_expr, self.now_dt.datetime)
        while True:
            self.next_start_dt = cron_iter.get_next(datetime)
            self.next_end_dt = (
                self.next_start_dt
                + timedelta(hours=self.duration_hours, seconds=-1))
            timeout = self.time_until(self.next_start_dt)
            self.env.process(self.end_cond())

            self.info(
                'Cron scheduled for '
                f'{self.next_start_dt.strftime("%Y-%m-%d %H:%M:%S")} - '
                f'{self.next_end_dt.strftime("%Y-%m-%d %H:%M:%S")}'
            )

            yield self.env.timeout(timeout)
            self.start()

    def end_cond(self):
        if self.next_end_dt is None:
            raise ValueError('End time cannot be determined')

        yield self.env.timeout(self.time_until(self.next_end_dt))
        self.stop()


class OperatingSchedule(Base):

    active_block = Monitor()

    """Controls the "program" -attribute of a machine"""
    def __init__(self, env, machine, blocks=None, disabled=False):
        super().__init__(env, name='OperatingSchedule')
        self.machine = machine
        self.active_block = None
        self.blocks = [
            CronBlock(self.env, '30 8 * * *', 3, 0),
            CronBlock(self.env, '30 11 * * *', 0.5, 0),
            CronBlock(self.env, '00 12 * * *', 2, 1),
            CronBlock(self.env, '00 14 * * *', 2, 0)
        ]
        for block in self.blocks:
            block.assign_schedule(self)

        self.disabled = disabled
        self.procs = {
            'schedule': self.env.process(self._schedule()),
            'on_machine_start': self.env.process(self._on_machine_start())
        }
        self.events = {
            'block_started': self.env.event(),
            'block_finished': self.env.event(),
            'block_deleted': self.env.event()
        }

    def _on_machine_start(self):
        while True:
            yield self.machine.events['switched_on_from_off']
            if self.disabled:
                pass
            elif self.active_block and self.active_block.program is not None:
                program = self.active_block.program
                self.debug(f'Setting program "{program}" at machine start')
                self.env.process(
                    self.machine._automated_program_switch(program))

    def _schedule(self):
        while True:
            # Wait until block is started
            block = yield self.events['block_started']
            self.debug(f'Schedule block {block} started')

            # Stop existing block and activate new
            if self.active_block is not None and self.active_block != block:
                assert not self.active_block.is_active
            assert block.is_active
            self.active_block = block

            # Start program
            program = self.active_block.program
            if program is None:
                raise ValueError('Block is missing program')
            if (not self.disabled
                    and self.machine.state not in ['off', 'error']):
                self.env.process(
                    self.machine._automated_program_switch(program))

            yield self.events['block_finished']
            self.active_block = None
            if (not self.disabled
                    and self.machine.state not in ['off', 'on', 'error']):
                self.debug('Switching to on')
                self.env.process(self.machine._switch_on(priority=-2))
            self.debug(f'Schedule block {block} finished')
