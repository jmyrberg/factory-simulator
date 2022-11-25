"""Machine in a factory."""


import arrow
import simpy

from src.base import Base
from src.causes import BaseCause, ManualSwitchOffCause, \
    ManualStopProductionCause, AutomatedStopProductionCause
from src.consumable import Consumable
from src.issues import ProductionIssue, OverheatIssue
from src.program import Program
from src.schedule import OperatingSchedule
from src.utils import ignore_preempted


class Machine(Base):

    def __init__(self, env):
        """Machine in a factory.

        Possible state changes:
            off -> on: 
            on -> idle: 
            idle -> on: 
            on -> error: 
        """
        super().__init__(env, name='Machine')
        # Resources
        self.ui = simpy.PreemptiveResource(env)  # user actions
        self.execute = simpy.PreemptiveResource(env)  # commands
        self.state = 'off'
        self.states = ['off', 'on', 'production', 'error']
        self.schedule = None  # OperatingSchedule(env, self)
        self.programs = {
            0: Program(
                env,
                bom={
                    'raw-material': {
                        'consumable': Consumable(env),
                        'rate': 5 / (60 * 15)  # = 5 units per 15 mins
                    }
                }
            )
        }
        self.program = 0
        self.production_interruption_ongoing = False

        # Statistics
        # TODO: Convert these to "Sensor" class or sth
        self.temperature = None
        self.room_temperature = None

        self.data = {}
        self.events = {
            # Program
            'switching_program': self.env.event(),
            'switched_program': self.env.event(),
            # User
            'on_button_pressed': self.env.event(),
            'off_button_pressed': self.env.event(),
            'start_buttion_pressed': self.env.event(),
            'stop_button_pressed': self.env.event(),
            'killswitch_pressed': self.env.event(),
            # Internal state change
            'state_change': self.env.event(),
            # Off
            'switching_off': self.env.event(),
            'switched_off': self.env.event(),
            # On
            'switching_on': self.env.event(),
            'switched_on': self.env.event(),
            'switched_on_from_off': self.env.event(),
            # Production
            'switching_production': self.env.event(),
            'switched_production': self.env.event(),
            'production_started': self.env.event(),
            'production_stopped': self.env.event(),
            'production_stopped_from_error': self.env.event(),
            'production_interrupted': self.env.event(),
            # Error
            'switching_error': self.env.event(),
            'switched_error': self.env.event(),
            'issue_occurred': self.env.event(),
            'issue_cleared': self.env.event(),
            'clearing_issue': self.env.event(),
            # Schedule
            'switching_program_automatically': self.env.event(),
            'switched_program_automatically': self.env.event(),
            # Other
            'temperature_change': self.env.event()
        }
        self.procs = {
            'room_temperature': self.env.process(self._room_temperature()),
            'temperature': self.env.process(self._temperature()),
            'temperature_monitor':
                self.env.process(self._temperature_monitor())
        }

    def _room_temperature(self):
        while True:
            ts = arrow.get(self.env.now).to('Europe/Helsinki')
            if 4 <= ts.month and ts.month <= 8:
                season_avg = 22
            else:
                season_avg = 18
            if 23 <= ts.hour or ts.hour <= 7:
                hour_norm = -self.pnorm(1, 1)
            else:
                hour_norm = self.norm(0, 0.1)

            self.room_temperature = season_avg + hour_norm
            # self.debug(f'Room temperature: {self.room_temperature}')
            yield self.env.timeout(60)

    def _temperature_monitor(self):
        yield self.env.timeout(2)
        while True:
            yield self.events['temperature_change']
            if self.temperature > 80:
                issue = OverheatIssue(self.temperature, 80)
                yield self.env.process(self._trigger_issue(issue))
            elif self.temperature > 70:
                self.warning(f'Temperature very high: {self.temperature}')

    def _temperature(self):
        # TODO: Sometime very high temperatures (check Kaggle for reference)
        # TODO: Overheat monitoring process
        # TODO: Cleanup
        # TODO: Collect data
        yield self.env.timeout(1)
        self.temperature = self.room_temperature
        last_change_time = self.env.now
        time_resolution = 60
        change_per_hour = {
            'production': 10,
            'on': 1,
            'idle': -3,
            'off': -5,
            'error': -5
        }
        while True:
            # Wait for state change that affects the temperature
            timeout = self.env.timeout(time_resolution)
            state_change = self.events['state_change']
            yield timeout | state_change
            if not state_change.processed:  # From timeout
                state = self.state
            else:
                state = state_change.value

            duration = self.env.now - last_change_time
            duration_hours = duration / 60 / 60
            last_change_time = self.env.now

            # Change depends on the duration of the previous state
            # The further away from room temperature, the faster the cooling
            delta_room = (
                (self.room_temperature - self.temperature)
                / 20 * duration_hours
            )  # = ~5 degrees in an hour if difference is 100
            delta_mode = change_per_hour[state] * duration_hours
            new_temp = self.temperature + delta_mode + delta_room
            noise = self.norm(0, duration_hours)
            self.temperature = max(self.room_temperature, new_temp) + noise
            # self.debug(f'{duration / 60 / 60:.2f} hours spent in "{state}"')
            # self.debug(f'Machine temperature: {self.temperature:.2f}')
            # yield self.env.timeout(60)

    @ignore_preempted
    def _switch_on(self, require_executor=True, priority=0, max_wait=0):
        """Change machine state to "on".

        State changes:
        off        -> on: Yes
        on         -> on: No
        production -> on: Yes
        error      -> on: No

        Possible actions:
        - Change settings, e.g. program or schedule
        """
        yield self.env.timeout(1)
        if self.state not in ['off', 'production']:
            self.warning(f'Cant go from state "{self.state}" to "on"')
        elif self.state == 'on':
            self.warning('Switching from "on" to "on"')
            self._trigger_event('switched_on')

        with self.execute.request(priority=priority) as executor:
            results = yield executor | self.env.timeout(max_wait)
            if executor not in results:
                self.debug('Execution ongoing, will not try to go "on"')
                return

            # Turn machine on
            if self.state == 'off':
                self._trigger_event('switching_on')
                yield self.env.timeout(1)
                self.state = 'on'
                self._trigger_event('switched_on')
                self._trigger_event('switched_on_from_off')
            elif self.state == 'production':
                self._trigger_event('switching_on')

                # Stop production gracefully
                if not self.production_interruption_ongoing:
                    cause = ManualSwitchOffCause(force=False)
                    self.env.process(self._interrupt_production(
                        cause, require_executor=False))
                    yield self.events['production_stopped']

                yield self.env.timeout(1)
                self.state = 'on'
                self._trigger_event('switched_on')

    def press_on(self):
        yield self.env.timeout(1)
        self._trigger_event('on_button_pressed')
        yield from self._switch_on()

    @ignore_preempted
    def _switch_off(self, emergency=False, require_executor=True,
                    priority=0, max_wait=0):
        """Change machine state to "off".

        State changes:
        off        -> off: No
        on         -> off: Yes
        production -> off: Yes (gracefully or emergency)
        error      -> off: Yes
        """
        yield self.env.timeout(1)
        if self.state == 'off':
            self.warning(f'Cant go from state "{self.state}" to "off"')
            self._trigger_event('switched_off')
            return

        priority = -9999 if emergency else priority
        with self.execute.request(priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug('Execution ongoing, will not try to go "off"')
                    return
            else:
                self.warning(
                    'Skipping executor waiting at switching off')

            # Turn machine off
            if self.state == 'on':
                self._trigger_event('switching_off')
                yield self.env.timeout(1)
                self.state = 'off'
                self._trigger_event('switched_off')
            elif self.state == 'production':
                self._trigger_event('switching_off')

                # Try interrupt production
                cause = ManualSwitchOffCause(force=emergency)
                self.env.process(self._interrupt_production(
                    cause, require_executor=False, priority=priority))
                self.debug('Waiting for production to stop')
                yield self.events['production_stopped']

                yield self.env.timeout(1)
                self.state = 'off'
                self._trigger_event('switched_off')
            elif self.state == 'error':
                self._trigger_event('switching_off')

                # Try interrupt production
                cause = ManualSwitchOffCause(force=True)
                yield self.env.process(
                    self._interrupt_production(cause, require_executor=False))

                yield self.env.timeout(1)
                self.state = 'off'
                self._trigger_event('switched_off')

    def press_off(self, emergency=False, priority=-1, max_wait=120):
        self._trigger_event('off_button_pressed')
        yield from self._switch_off(
            emergency=emergency, priority=priority, max_wait=max_wait)

    def _switch_production(
            self, require_executor=True, priority=0, max_wait=0):
        """Change machine state to "off".

        State changes:
        off        -> production: No, always through "on"
        on         -> production: Yes
        production -> production: No
        error      -> production: No
        """
        yield self.env.timeout(1)
        if not self.state == 'on':
            self.warning(f'Cant go from state "{self.state}" to "production"')
            return

        with self.execute.request(priority=priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug(
                        'Execution ongoing, will not try to go "production"')
                    return
            else:
                self.warning(
                    'Skipping executor waiting at switching production')

            # Start production
            self._trigger_event('switching_production')
            yield self.env.timeout(1)
            self.procs['production'] = self.env.process(self._production())
            self.state = 'production'
            self._trigger_event('switched_production')

    @ignore_preempted
    def _switch_program(self, program, require_executor=True, max_wait=10):
        """Switch program on machine

        State:
        off        : Yes (internally only)
        on         : Yes
        production : No
        error      : Yes (internally only)
        """
        if program not in self.programs:
            self.error(f'Program "{program}" does not exist, returning')
            return

        yield self.env.timeout(1)
        if self.state == 'production':
            self.warning(
                'Cant change program during production run, please '
                'stop production first')
            return

        with self.execute.request() as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug(f'Timed out when trying to switch program to '
                               f'{program}')
                    return
            else:
                self.warning(
                    'Skipping executor waiting at switching program')

            assert self.state != 'production', 'Something went wrong :('
            self._trigger_event('switching_program')
            yield self.env.timeout(1)
            self.program = program
            self._trigger_event('switched_program')

    @ignore_preempted
    def _automated_program_switch(self, program, force=False):
        """Switch production program automatically."""
        if program not in self.programs:
            self.error(f'Program "{program}" does not exist, returning')
            return
        if self.state == 'error':
            self.warning('Automated program not possible in "error" state')

        self._trigger_event('switching_program_automatically')

        if self.state == 'error':
            self.warning('Ignoring schedule in "error" state, returning')
            return

        yield self.env.timeout(1)

        cause = AutomatedStopProductionCause(force=force)
        self.env.process(self._interrupt_production(cause))
        yield self.events['production_stopped']

        self.env.process(self._switch_on(max_wait=120))
        yield self.events['switched_on']

        self.env.process(self._switch_program(program, max_wait=120))
        yield self.events['switched_program']

        self.env.process(self._switch_production())
        yield self.events['production_started']

        self._trigger_event('switched_program_automatically')

    @ignore_preempted
    def switch_program(self, program, priority=-1, max_wait=60):
        yield self.env.timeout(1)
        with self.ui.request() as ui:
            results = yield ui | self.env.timeout(0)
            if ui not in results:
                self.debug(
                    'UI is not responsive, will not try to go "production"')
                return

            self.env.process(self._switch_program(
                program, priority=priority, max_wait=max_wait))
            yield self.events['switched_program']

    def start_production(self, program=None, max_wait=60):
        yield self.env.timeout(1)
        with self.ui.request() as ui:
            results = yield ui | self.env.timeout(0)
            if ui not in results:
                self.debug(
                    'UI is not responsive, will not try to go "production"')
                return

            if program is not None:
                yield self.env.process(self._switch_program(
                    program, max_wait=max_wait))

            self.env.process(self._switch_production())

    def stop_production(self, force=False):
        yield self.env.timeout(1)
        with self.ui.request() as ui:
            results = yield ui | self.env.timeout(0)
            if ui not in results:
                self.debug(
                    'UI is not responsive, cannot try to stop production')
                return

            cause = ManualStopProductionCause(force=force)
            self.env.process(self._interrupt_production(cause))

    def _interrupt_production(
            self, cause=None, require_executor=True, priority=0):
        if self.production_interruption_ongoing:
            self.warning('Production interruption already ongoing, returning')
            return

        yield self.env.timeout(1)
        with self.execute.request(priority=priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(120)
                if executor not in results:
                    self.debug('Execution ongoing, wont interrupt production')
                    return
            else:
                self.warning(
                    'Skipping executor waiting at interrupt production')

            if not self.production_interruption_ongoing:
                production_proc = self.procs.get('production')
                if production_proc and production_proc.is_alive:
                    production_proc.interrupt(cause)
            else:
                self.warning(
                    'Cannot interrupt production, its ongoing already')

    def _production(self):
        """Machine producing products.

        State changes:
        production -> production: No, always through "on"
        on         -> production: Yes
        production -> production: No
        error      -> production: No
        """
        yield self.env.timeout(1)
        # TODO: Failure probability etc.
        # TODO: Look at what was originally asked for and implement
        # TODO: Cleanup the triggers + prio handling with try etc.
        if self.program is None:
            self.warning('Production cannot be started with no program set')
            return

        while True:
            self._trigger_event('production_started')
            try:
                # Run one batch of program
                self.procs['program_run'] = (
                    self.env.process(self.programs[self.program].run()))
                yield self.procs['program_run']
            except simpy.Interrupt as i:
                self.info(f'Production interrupted: {i}')
                self._trigger_event('production_interrupted')
                self.production_interruption_ongoing = True
                cause_or_issue = i.cause

                # Causes are reasons to interrupt batch process
                if isinstance(cause_or_issue, BaseCause):
                    self.procs['program_run'].interrupt(cause_or_issue)
                    yield self.procs['program_run']

                # Issues need to be resolved by operators but cause batch
                # interruption, if the batch is still running
                elif isinstance(cause_or_issue, ProductionIssue):
                    yield self.env.process(self._switch_error(cause_or_issue))
                    # FIXME: Are we sure that production can't be in progress?
                    self._trigger_event('production_stopped_from_error')
                else:
                    raise i
                self._trigger_event('production_stopped')
                break

        if self.state == 'production':
            yield self.env.process(self._switch_on())

        self.production_interruption_ongoing = False

    def _switch_error(self, issue):
        """Machine is in erroneous state.

        State changes:
        off        -> error: No
        on         -> error: Yes
        production -> error: Yes
        error      -> error: No
        """
        yield self.env.timeout(1)
        if self.state not in ['on', 'production']:
            self.warning(f'Cant go from state "{self.state}" to "error"')
            return

        self._trigger_event('issue_occurred', issue)
        self._trigger_event('switching_error')
        with self.ui.request(priority=-9999) as ui:
            yield ui  # Should get immediately based on priority

            with self.execute.request(priority=-9999) as executor:
                yield executor

                yield self.env.timeout(1)
                self.state = 'error'
                self._trigger_event('switched_error')

                # Try stop production
                if self.state == 'production':
                    yield self.env.process(self._interrupt_production(
                        issue, require_executor=False))
                    yield self.events['production_stopped_from_error']

                # Give execution back once clear issue from operator
                yield self.events['clearing_issue']

            self.debug('Execution released')

            # UI locked until issue cleared entirely
            yield self.events['issue_cleared']

        self.debug('UI released')

    def reboot(self, priority=-1):
        if self.state == 'off':
            self.warning('Tried to reboot machine that is "off"')
            return

        self.env.process(self._switch_off(
            require_executor=False, priority=priority))
        yield self.events['switched_off']
        self.env.process(self._switch_on(
            require_executor=False, priority=priority))
        yield self.events['switched_on']
        self.debug('Rebooted')

    def clear_issue(self):
        """Clear an existing issue."""
        if self.state == 'error':
            self._trigger_event('clearing_issue')
            yield self.env.timeout(10)
            yield self.env.process(self.reboot())
            self._trigger_event('issue_cleared')
        else:
            self.warning('No issues to be cleared')
            return
