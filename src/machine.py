"""Machine in a factory."""


import simpy

from src.base import Base
from src.causes import BaseCause, ManualSwitchOffCause
from src.consumable import Consumable
from src.issues import ProductionIssue
from src.program import Program


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
        # User interface - limits what user can do
        self.ui = simpy.PriorityResource(env)
        self.state = 'off'
        self.states = ['off', 'idle', 'on', 'production', 'error']
        self.programs = {
            0: None,
            1: Program(
                env,
                bom={
                    'raw-material': {
                        'consumable': Consumable(env),
                        'rate': 5 / (60 * 15)  # = 5 units per 15 mins
                    }
                }
            )
        }
        self.program = self.programs[0]

        self.data = []
        self.events = {
            'switching_program': self.env.event(),
            'switched_program': self.env.event(),
            **{f'switching_{s}': self.env.event() for s in self.states},
            **{f'switched_{s}': self.env.event() for s in self.states},
            'issue': self.env.event(),
            'issue_cleared': self.env.event()
        }
        self.procs = {}

    def _set_state(self, state, *args, wait=False, **kwargs):
        if self.state != state:
            self._trigger_event(f'switching_{state}')
            yield self.env.timeout(10)  # TODO: Randomize/from-to dependent

            func = getattr(self, f'_{state}')
            self.procs[state] = self.env.process(func(*args, **kwargs))
            if wait:
                yield self.procs[state]

            self.state = state
            self.log(f'{state.upper()}')
            self._trigger_event(f'switched_{state}')

    def _resume_state(self):
        func = getattr(self, f'_{self.state}')
        self.procs[self.state] = self.env.process(func())

    def clear_issue(self):
        self.events['issue'] = self.env.event()
        yield self.env.timeout(1)  # TODO: Randomize
        self.events['issue_cleared'].succeed()
        self.events['issue_cleared'] = self.env.event()
        yield self.env.process(self._set_state('on'))

    def _trigger_issue(self, issue):
        yield self.env.timeout(1)  # TODO: Randomize

        # Ensure operating mode is error
        self.env.process(self._set_state('error'))

        # Lock UI and trigger "issue" event
        with self.ui.request(priority=-1) as req:
            yield req
            yield self.env.timeout(1)  # TODO: Randomize
            self.events['issue'].succeed(issue)

            # Wait for issue to be cleared by someone (=self.clear_issue())
            yield self.env.timeout(1)
            yield self.events['issue_cleared']

    def switch_on(self):
        yield self.env.timeout(1)
        if self.state != 'on':
            with self.ui.request() as req:
                yield req
                self.env.process(self._set_state('on'))

    def switch_off(self, force=False):
        yield self.env.timeout(1)
        if self.state != 'off':
            with self.ui.request() as req:
                yield req
                self.env.process(
                    self._set_state('off', wait=True, force=force))

    def _switch_program(self, program):
        if self.programs[program] != self.program:
            self._trigger_event('switching_program')
            self.program = self.programs[program]
            yield self.env.timeout(10)  # TODO: Randomize + which possible?
            self._trigger_event('switched_program')

    def switch_program(self, program):
        if self.state != 'off':
            yield self.env.timeout(1)
            with self.ui.request() as req:
                yield req
                yield from self._switch_program(program)

    def _interrupt_production(self, cause=None):
        production_proc = self.procs.get('production')
        if production_proc and production_proc.is_alive:
            production_proc.interrupt(cause)

    def _off(self, force=False):
        yield self.env.timeout(2)  # TODO: Randomize

        # If production is ongoing, interrupt gracefully (force=False)
        # or with force (force=True)
        self._interrupt_production(ManualSwitchOffCause(force=force))

        # No production automatically when switched on
        if self.program is not None:
            self.env.process(self._switch_program(0))
            yield self.events['switched_program']

        yield self.env.timeout(30)  # TODO: Randomize + dependencies?

    def _idle(self):
        while True:  # Idle mode is only possible when program = 0
            yield self.env.timeout(1)  # TODO: Randomize
            if self.program is not None:
                self.env.process(self._set_state('on'))
                break
            else:
                yield self.events['switched_program']

    def _error(self):
        yield self.events['issue_cleared']  # Wait until issue cleared
        yield self.env.timeout(1)  # TODO: Randomize

    def _production(self):
        # TODO: Failure probability etc.
        # TODO: Look at what was originally asked for and implement
        while True:
            try:
                # Run one batch of program
                self.procs['program_run'] = (
                    self.env.process(self.program.run()))
                yield self.procs['program_run']
            except simpy.Interrupt as i:
                self.log(f'Production interrupted: {i}')
                cause_or_issue = i.cause

                # Causes are reasons to interrupt batch process
                if isinstance(cause_or_issue, BaseCause):
                    self.procs['program_run'].interrupt(cause_or_issue)

                # Issues need to be resolved by operators but cause batch
                # interruption, if the batch is still running
                elif isinstance(cause_or_issue, ProductionIssue):
                    yield self.env.process(self._trigger_issue(cause_or_issue))
                    # FIXME: Are we sure that production can't be in progress?
                else:
                    raise i
                break

    def _on(self):
        yield self.env.timeout(1)  # TODO: Randomize
        if self.program is None:
            yield self.env.process(self._set_state('idle'))
        else:
            yield self.env.process(self._set_state('production'))
