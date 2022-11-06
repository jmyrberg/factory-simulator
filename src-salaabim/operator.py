"""Module for operator."""


import salabim as sim


class Operator(sim.Component):

    def setup(self, arrival_hour=8, lunch_hour=12, leave_hour=17):
        self.arrival_hour = arrival_hour
        self.lunch_hour = lunch_hour
        self.leave_hour = leave_hour

        # Internal state
        # home, lunch, work
        self.state = sim.State('operator_state', 'home')
        self.had_lunch = sim.State('had_lunch', False)

        self._init_animations()

    def _init_animations(self):
        base_x_offset = 50
        states = ['home', 'work', 'lunch']
        sim.AnimateMonitor(
            self.state.all_monitors()[-1],
            title='Operator state',
            vertical_map=lambda x: states.index(x),
            labels=states,
            x=base_x_offset,
            y=200,
            height=100,
            width=400,
            linewidth=2,
            horizontal_scale=0.25,
            vertical_scale=30,
            vertical_offset=20
        )

    def _get_next_work_arrival(self):
        # TODO: Probability of being sick?

        # If weekend, don't go to work
        dt = self.env.t_to_datetime(self.env.t())
        if dt.day in (9, 10):  # (5 ,6)
            print('Not going to work today as it is weekend! :)')
            next_workday = 1
        else:
            next_workday = dt.day + 1

        next_hour = self.arrival_hour
        next_minutes = 0
        early_or_late_minutes = int(
            self.env.minutes(sim.Uniform(-5, 15).sample()))
        next_minutes += early_or_late_minutes
        next_seconds = int(sim.Uniform(0, 60).sample())
        arrival_dt = dt.replace(
            day=next_workday,
            hour=next_hour,
            minute=max(min(next_minutes, 60), 0),
            second=next_seconds
        )

        print(f'Next work arrival: {arrival_dt}')
        return self.env.datetime_to_t(arrival_dt)

    def home(self):
        while True:
            self.state.set('home')
            if self.machine:
                self.machine.switch_off()

            self.had_lunch.set(False)
            yield self.activate(
                process='work', at=self._get_next_work_arrival())

    def lunch(self):
        while True:
            self.state.set('lunch')
            if self.machine:
                self.machine.switch_off()

            yield self.hold(self.env.minutes(sim.Uniform(20, 40).sample()))
            self.had_lunch.set(True)

            yield self.activate(process='work')

    def _get_next_work_event(self):
        dt = self.env.t_to_datetime(self.env.t())
        if not self.had_lunch():
            at = dt.replace(hour=11, minute=45)
            yield self.activate(process='lunch', at=self.env.datetime_to_t(at))
        else:
            at = dt.replace(hour=17, minute=0)
            yield self.activate(process='home', at=self.env.datetime_to_t(at))

    def assign_machine(self, machine):
        self.machine = machine

    def work(self):
        while True:  # = "oravanpyörä"
            # Turn the machine on
            if self.machine.state() == 'off':
                self.machine.state.set('on')

            # Turn a program on
            if self.machine.program() == 0:
                self.machine.program.set(1)

            yield from self._get_next_work_event()

            self.machine.activate()

    def process(self):
        while True:
            if self.state() == 'home':
                yield from self.home()
            elif self.state() == 'work':
                yield from self.work()
            elif self.state() == 'lunch':
                yield from self.lunch()
