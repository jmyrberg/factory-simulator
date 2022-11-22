"""Schedules."""


from datetime import datetime, timedelta

import arrow
import simpy

from croniter import croniter

from src.base import Base


class Block(Base):
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
            self.debug('Starting')
            self._trigger_event('start')

    def stop(self):
        """Deactivate block from outside."""
        if self.is_active:
            self.debug('Stopping')
            self._trigger_event('stop')
        else:
            self.warning('Tried to stop an active block')

    def assign_schedule(self, schedule):
        self.schedule = schedule

    def assign_program(self, program):
        self.program = program

    def _run(self):
        while True:
            try:
                self.debug('Waiting for block to start')

                # Wait for start
                yield self.events['start']

                # Start
                self._trigger_event('started')
                self.is_active = True

                # Trigger block activation in schedule
                if self.schedule:
                    self.schedule._trigger_event('block_started', self)
                else:
                    self.warning('No schedule to trigger')

                # Stop
                yield self.events['stop']
                self.debug('Set is_activate=False')
                self.is_active = False

                # Trigger block stop in schedule
                self.schedule._trigger_event('block_finished', self)
            except simpy.Interrupt:  # = delete
                self.is_active = False
                # Trigger block stop in schedule
                self.schedule._trigger_event('block_deleted', self)
                break


class CronBlock(Block):
    def __init__(self, env, start_expr, duration_hours, program=None):
        super().__init__(env, program, name=f'CronBlock({start_expr})')
        self.start_expr = start_expr
        self.duration_hours = duration_hours
        self.next_start_dt = None
        self.next_end_dt = None

        self.env.process(self.start_cond())

    def start_cond(self):
        cron_iter = croniter(self.start_expr, self.now_dt.datetime)
        while True:
            self.next_start_dt = cron_iter.get_next(datetime)
            self.next_end_dt = (
                self.next_start_dt + timedelta(hours=self.duration_hours))
            timeout = self.time_until(self.next_start_dt)
            self.debug(f'Next start time: {self.next_start_dt}')
            self.env.process(self.end_cond())
            yield self.env.timeout(timeout)
            self.start()

    def end_cond(self):
        if self.next_end_dt is None:
            raise ValueError('End time cannot be determined')
        self.debug(f'Next end time: {self.next_end_dt}')
        self.debug(f'Will wait {self.time_until(self.next_end_dt)} seconds')
        yield self.env.timeout(self.time_until(self.next_end_dt))
        self.stop()


class OperatingSchedule(Base):
    """Controls the "program" -attribute of a machine"""
    def __init__(self, env, machine, blocks=None):
        super().__init__(env, name='OperatingSchedule')
        self.machine = machine
        self.active_block = None
        self.blocks = [
            CronBlock(self.env, '30 8 * * *', 3, 1),
            CronBlock(self.env, '30 11 * * *', 0.5, 0),
            CronBlock(self.env, '00 12 * * *', 2, 1),
            CronBlock(self.env, '00 14 * * *', 2, 1)
        ]
        for block in self.blocks:
            block.assign_schedule(self)

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
            yield self.machine.events['switched_from_off_to_on']
            yield self.machine.events['switched_on']
            if self.active_block and self.active_block.program:
                program = self.active_block.program
                self.debug(f'Setting program "{program}" at machine start')
                self.env.process(self.machine.switch_program(program))

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
            self.env.process(self.machine.switch_program(program))

            yield self.events['block_finished']
            self.active_block = None
            self.env.process(self.machine.switch_program(0))  # idle
            self.debug(f'Schedule block {block} finished')
