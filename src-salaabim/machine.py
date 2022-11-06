"""Module for machine."""


import salabim as sim


class Machine(sim.Component):

    def setup(self, consumption_per_batch=100, consumption_speed=10):
        self.consumption_per_batch = consumption_per_batch
        self.consumption_speed = consumption_speed

        # Internal states
        # Possible states: ('off', 'idle', 'on', 'error')
        self.state = sim.State('machine_state', 'off')
        # Programs (0 = None, 1, 2, ...)
        self.program = sim.State('program', 0)
        self.message = sim.State('message', '')
        self.production_in_progress = sim.State('production_in_progress', False)
        self.error_code = sim.State('error_code', 0)  # > 500 => mechanic
        self.error_message = sim.State('error_message', '')
        self.temperature = sim.State('temperature', 0)
        # self.planned_operating_time = PlannedOperatingTime(machine=self)

        self._init_animations()

    def _init_animations(self):
        base_x_offset = 50
        states = ['off', 'idle', 'on', 'error']
        sim.AnimateMonitor(
            self.state.all_monitors()[-1],
            title='Machine state',
            vertical_map=lambda x: states.index(x),
            labels=states,
            x=base_x_offset,
            y=400,
            height=100,
            width=400,
            linewidth=2,
            horizontal_scale=0.25,
            vertical_scale=30,
            vertical_offset=10
        )

    # def production_process(self):
    #     if self.can_start_production():
    #         print('Production can be started')
    #         self.production_in_progress.set(True)

    #         # TODO: Different programs have different consumption etc.

    #         # Take raw materials from tank
    #         print('Getting raw materials from tank')
    #         yield self.get((tank_level, self.consumption_per_batch))

    #         # Wait until production ready
    #         print('Waiting until production ready')
    #         yield self.hold(
    #             self.consumption_per_batch / self.consumption_speed)

    #         # Output of batch
    #         env.produced_parts += 20
    #         m.tally(env.produced_parts)

    #         # Wait random time after each batch?
    #         yield self.hold(env.seconds(sim.Uniform(30, 60)))

    #         self.production_in_progress.set(False)

    def set_state(self, to_state, at=None):
        from_state = self.state()
        if from_state == to_state:
            print(f'Warning: Already in state "{to_state}"!')

        if at is not None:
            yield self.hold(till=at)

        self.state.set(to_state)
        yield self.activate(process=to_state)

    def off(self):
        while True:
            yield self.cancel()
            # yield self.wait((self.state, lambda x, *_: x != 'off'))

    def idle(self):
        while True:
            yield self.cancel()
            # yield self.wait((self.state, lambda x, *_: x != 'idle'))

    def error(self):
        while True:
            yield self.wait((self.state, lambda x, *_: x != 'error'))

    def run_program(self):
        while True:
            if self.state() != 'on' or self.program() <= 0:
                yield self.cancel()

            self.production_in_progress.set(True)

            yield self.hold(self.env.minutes(10))
            self.env.produced_parts += 20

            self.production_in_progress.set(False)

    def on(self):
        while True:
            if self.program() > 0:
                yield self.activate(process='run_program')
            else:
                yield from self.set_state('idle')

    def process(self):
        while True:
            if self.state() == 'off':
                yield from self.off()
            if self.state() == 'on':
                yield from self.on()
            elif self.state() == 'idle':
                yield from self.idle()
            else:
                yield from self.error()

    def switch_on(self):
        yield from self.set_state('on')

    def switch_off(self):
        self.program.set(0)
        self.state.set('off')

    def switch_program(self, program=0):
        self.program.set(program)
        yield from self.set_state('on')
