"""Module for machine."""


import salabim as sim


class Machine(sim.Component):

    def setup(self, consumption_per_batch=100, consumption_speed=10):
        self.consumption_per_batch = consumption_per_batch
        self.consumption_speed = consumption_speed

        # Internal states
        # Possible states: ('off', 'idle', 'on', 'error')
        self.state = sim.State('state', 'off')
        # Programs (0 = None, 1, 2, ...)
        self.program = sim.State('program', 0)
        self.message = sim.State('message', '')
        self.production_in_progress = sim.State('production_in_progress', False)
        self.error_code = sim.State('error_code', 0)  # > 500 => mechanic
        self.error_message = sim.State('error_message', '')
        self.temperature = sim.State('temperature', 0)
        # self.planned_operating_time = PlannedOperatingTime(machine=self)

    def reset_defaults(self):
        self.program.set(0)
        self.message.set('')
        self.production_in_progress.set(False)

    def log(self, level, message):
        self.message.set(f'[{level.upper()}]: {message}')

    def set_error(self, code, message):
        self.state.set('error')
        self.error_code.set(code)
        self.error_message.set(message)

    def _clear_error(self):
        self.state.set('idle')
        self.error_code.set(0)
        self.error_message.set('')

    def fix_error(self):
        self.state.set('idle')
        if self.error_code() == 101:  # Tank level
            yield self.hold(self.env.minutes(60))
            yield self.put((tank_level, 1_000))

        self._clear_error()

    def get_error_message(code):
        return {
            
            # Require mechanic -->
            501: 'Severe failure, please call the mechanic'
        }.get(code, f'Error code: {code}')

    def can_switch_on(self):
        # TODO: Some probability of being in an error state for X time
        if self.state() == 'error':
            self.set_error(self.error_code())
            return self.error_code() < 500
        elif self.state() == 'on':
            return False
        else:
            return True

    def switch_on(self):
        if self.can_switch_on():
            # if self.state.get() == 'off':
            #     yield self.hold(env.seconds(sim.Uniform(30, 60).sample()))
            # elif self.state.get() == 'idle':
            #     yield self.hold(env.seconds(sim.Uniform(10, 20).sample()))
            self.state.set('on')

    def can_switch_off(self):
        if self.state() == 'error':
            return False

        if self.production_in_progress():
            self.set_error(100, 'Shut down while production was ongoing')

        return True

    def switch_off(self):
        if self.can_switch_off():
            self.state.set('off')
            self.reset_defaults()
            # TODO: Some kind of temperature-dependent cleanup waiting time
            yield self.hold(env.seconds(sim.Uniform.sample(30, 60).sample()))

    def can_set_idle(self):
        if self.state() == 'error':
            return False

        if self.production_in_progress():
            self.log('warning',
                     'Cannot set "idle" while production in progress')
            return False

        return True

    def set_idle(self):
        if self.can_set_idle():
            self.state.set('idle')

    def set_program(self, program):
        self.program.set(program)

    def can_start_production(self):
        if tank_level.available_quantity() < 100:
            self.set_error(101, 'Tank level < 100, cannot start production')
            return False

        if self.production_in_progress():
            self.log('warning', 'Production already in progress')
            return False

        if self.program() == 0:
            self.log('warning', 'Please select program for production')
            return False

        if self.state() not in ('on', 'idle'):
            self.log('warning',
                     f'Cannot start production from state "{self.state()}"')
            return False
    
        return True

    def production_process(self):
        if self.can_start_production():
            print('Production can be started')
            self.production_in_progress.set(True)

            # TODO: Different programs have different consumption etc.

            # Take raw materials from tank
            print('Getting raw materials from tank')
            yield self.get((tank_level, self.consumption_per_batch))

            # Wait until production ready
            print('Waiting until production ready')
            yield self.hold(
                self.consumption_per_batch / self.consumption_speed)

            # Output of batch
            env.produced_parts += 20
            m.tally(env.produced_parts)

            # Wait random time after each batch?
            yield self.hold(env.seconds(sim.Uniform(30, 60)))

            self.production_in_progress.set(False)

    def process(self):
        while True:
            if self.state() == 'off':
                yield self.wait((self.state, lambda x, *_: x != 'off'))
            if self.state() == 'on':
                yield from self.production_process()
            elif self.state() == 'idle':
                yield self.wait((self.state, lambda x, *_: x != 'idle'))
            else:
                yield self.wait((self.state,
                                 lambda x, *_: x in ('on', 'off', 'idle')))
                yield self.passivate()

