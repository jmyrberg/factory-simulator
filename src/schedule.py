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
        program_name = program.name if program is not None else None
        name = f'Cron({start_expr}, {duration_hours}h, {program_name})'
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
    def __init__(self, env, blocks=None, name='operating-schedule'):
        super().__init__(env, name=f'OperatingSchedule({name})')
        self.blocks = blocks
        for block in self.blocks:
            block.assign_schedule(self)

        self.disabled = False
        self.machine = None
        self.active_block = None
        self.procs = {
            'schedule': self.env.process(self._schedule()),
            'on_machine_start': self.env.process(self._on_machine_start())
        }
        self.events = {
            'machine_assigned': self.env.event(),
            'block_started': self.env.event(),
            'block_finished': self.env.event(),
            'block_deleted': self.env.event()
        }

    def assign_machine(self, machine):
        self.machine = machine
        self.emit('machine_assigned')
        yield self.env.timeout(0)

    def _on_machine_start(self):
        while True:
            if self.machine is None:
                yield self.events['machine_assigned']

            if self.machine is not None:
                yield self.machine.events['switched_on_from_off']

            # NOTE: Not tested if machine unassigned?

            if (self.machine is not None
                    and self.active_block
                    and self.active_block.program is not None):
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

            if (self.machine is not None
                    and self.machine.state not in ['off', 'error']):
                self.env.process(
                    self.machine._automated_program_switch(program))

            yield self.events['block_finished']
            self.active_block = None
            if (self.machine is not None
                    and self.machine.state not in ['off', 'on', 'error']):
                self.debug('Switching to on')
                self.env.process(self.machine._switch_on(priority=-2))

            self.debug(f'Schedule block {block} finished')
