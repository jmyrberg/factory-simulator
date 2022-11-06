"""Models operator."""


import logging

import arrow
import simpy

from src.base import Base


logger = logging.getLogger(__name__)


class Machine(Base):

    def __init__(self, env):
        super().__init__(env, name='Machine')
        self.env = env
        self.state = 'off'
        self.states = ['off', 'idle', 'on', 'error']
        self.program = 0

        self.state_events = {
            'off': self.env.event(),
            'on': self.env.event()
        }
        self.state_procs = {
            'off': self.env.process(self.off()),
            'on': self.env.process(self.on())
        }

        self.data = []

        self.state_events['off'].succeed()

    def off(self):
        while True:
            self.log('Waiting for "off"...')
            yield self.state_events['off']
            self.log('Machine "off"...')
            self.state = 'off'
            self.state_events['off'] = self.env.event()

    def run_program(self):
        self.log(f'Running program {self.program}')
        yield self.env.timeout(self.minutes(15))

    def switch_on(self):
        self.state_events['on'].succeed()

    def switch_off(self):
        self.state_events['off'].succeed()
        self.state_procs['on'].interrupt('Switching off')

    def switch_program(self, program):
        self.program = program

    def on(self):
        # TODO: Failure probability etc.
        # TODO: Use tanks etc.
        while True:
            self.log('Waiting for "on"...')
            yield self.state_events['on']
            if self.program == 0:
                self.log('Machine "idle"...')
                self.state = 'idle'
            else:
                self.log('Machine "on"...')
                self.state = 'on'
                while True:
                    try:
                        run = self.env.process(self.run_program())
                        yield run
                        self.log('Production batch done!')
                    except simpy.Interrupt as i:
                        self.log(f'Production interrupted: {i}')
                        break

            self.state_events['on'] = self.env.event()

    def lunch(self):
        self.log('Eating lunch...')
        yield self.env.timeout(self.minutes(30))  # FIXME: Randomize
        self.log('Lunch done!')
