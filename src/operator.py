"""Module for operator."""


import salabim as sim


class Operator(sim.Component):
    def setup(self):
        self.at_work = sim.State('at_work', True)
        self.machine = None

    def attach_machine(self, machine):
        self.machine = machine

    def get_next_arrival(self):
        # TODO: Probability of being sick?

        # If weekend, don't go to work
        dt = self.env.t_to_datetime(self.env.t())
        if dt.day in (9, 10):
            print('Not going to work today as it is weekend! :)')
            next_workday = 1
        else:
            next_workday = dt.day + 1

        next_hour = 8
        next_minutes = 0
        early_or_late_minutes = int(self.env.minutes(sim.Uniform(-5, 15).sample()))
        next_minutes += early_or_late_minutes
        next_seconds = int(sim.Uniform(0, 60).sample())
        arrival_dt = dt.replace(
            day=next_workday,
            hour=next_hour,
            minute=next_minutes,
            second=next_seconds
        )

        print(f'Next work arrival: {arrival_dt}')
        return self.env.datetime_to_t(arrival_dt)

    def process(self):
        while True:  # = "oravanpyörä"
            # Arrive at work ~8-11
            print('Arriving at work')
            arrival = self.get_next_arrival()
            yield self.hold(till=arrival)

            # Turn on the machine
            print('Turning on the machine')
            self.machine.switch_on()
            self.machine.set_program(1)

            # TODO: Fix this wait etc.
            #       Needs to wait until tank filled etc.?
            yield self.wait((self.machine.state, 'error'),
                            fail_delay=self.env.hours(3.5))
            if not self.failed():  # Yes errors
                yield from self.machine.fix_error()

            self.machine.switch_off()

            # Go to lunch break
            yield self.hold(self.env.minutes(30))

            # Turn the machine back on
            self.machine.switch_on()
            self.machine.set_program(1)

            # Wait if errors / operate machine
            yield self.wait((self.machine.state, 'error'),
                            fail_delay=self.env.hours(3.5))
            if not self.failed():  # Yes errors
                self.machine.fix_error()

            # Go home
            self.machine.switch_off()
