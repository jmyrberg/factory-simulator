"""Schedules."""


from datetime import datetime, timedelta
from functools import partial, wraps, update_wrapper

import arrow
import simpy

from croniter import croniter

from src.base import Base
from src.maintenance import Maintenance
from src.issues import ScheduledMaintenanceIssue
from src.utils import Monitor


def get_action(name, *args, **kwargs):
    """Action called upon block start."""
    if 'schedule' in kwargs:
        raise ValueError('Reserved kwarg "schedule" given in "kwargs"')

    funcs = {
        'switch-program': _action_switch_program,
        'maintenance': _action_maintenance
    }
    func = partial(funcs[name], *args, **kwargs)
    args_str = ", ".join(args)
    kwargs_str = ', '.join(f'{k}={v!r}' for k, v in kwargs.items())
    func_name = f'{name}('
    if len(args_str) > 0:
        func_name += args_str + ', '
    if len(kwargs_str) > 0:
        func_name += kwargs_str
    func_name += ')'
    func.__name__ = func_name
    return func


def _action_switch_program(block, program_id):
    # TODO: Simplify block/schedule events
    block.emit('action_started')
    machine = block.schedule.machine
    if machine is None or program_id is None:
        raise ValueError('Machine or program_id is None')

    programs = [p for p in machine.programs if p.uid == program_id]
    if len(programs) == 0:
        raise ValueError(f'Unknown program "{program_id}”')
    program = programs[0]

    block.env.process(machine._automated_program_switch(program))

    yield block.events['stopped']
    if (machine is not None
            and machine.state not in ['off', 'on', 'error']):
        block.debug('Switching to on')
        block.env.process(machine._switch_on(priority=-2))

    block.emit('action_stopped')


def _action_maintenance(block):
    # TODO: Simplify block/schedule events
    block.emit('action_started')
    machine = block.schedule.machine
    maintenance = machine.maintenance
    duration = block.duration_hours * 60 * 60
    block.debug(f'Maintenance duration: {duration / 60 / 60} hours')
    issue = ScheduledMaintenanceIssue(machine, duration)
    block.env.process(maintenance.add_issue(issue))
    yield block.events['stopped']
    block.emit('action_stopped')


class Block(Base):

    is_active = Monitor()
    action = Monitor()

    def __init__(self, env, action=None, name='block'):
        """
        
        action (tuple): Tuple of (action_func, args, kwargs). Assigned machine
            will be automatically passed within kwargs.
        """
        super().__init__(env, name=name)
        self.action = action
        self.is_active = False
        self.deleted = False

        self.schedule = None
        self.events = {
            # Block related
            'start': self.env.event(),
            'started': self.env.event(),
            'stop': self.env.event(),
            'stopped': self.env.event(),
            # Action related
            'action_started': self.env.event(),
            'action_stopped': self.env.event()
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

    def assign_action(self, action):
        self.action = action

    def run_action(self):
        if self.action is not None:
            return self.action(block=self)
        else:
            self.warning('Tried to run action when action=None')

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

    def __init__(self, env, cron, duration_hours, action=None,
                 name='cron-block'):
        super().__init__(env, action=action, name=name)
        self.cron = cron
        self.duration_hours = duration_hours
        self.next_start_dt = None
        self.next_end_dt = None

        self.env.process(self.start_cond())

    def start_cond(self):
        cron_iter = croniter(self.cron, self.now_dt.datetime)
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
        super().__init__(env, name=name)
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

            if self.machine and self.active_block:
                block = self.active_block
                self.debug(f'Running block "{block}" at machine start')
                self.env.process(self.active_block.run_action())

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

            # Start action
            if (self.machine is not None
                    and self.machine.state not in ['off', 'error']):
                self.env.process(self.active_block.run_action())

            yield self.events['block_finished']
            self.active_block = None

            self.debug(f'Schedule block {block} finished')
