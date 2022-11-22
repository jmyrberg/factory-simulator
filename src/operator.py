"""Models operator."""


import arrow

from src.base import Base
from src.issues import LowConsumableLevelIssue, UnknownIssue


class Operator(Base):

    def __init__(self, env):
        """Models an operator at the factory.

        Basic cycle:
            1) Go to work in the morning, if it's not weekend
            2) Operate/monitor the machine
            3) Go to lunch
            4) Operate/monitor the machine
            5) Go home
        """
        super().__init__(env, name='Operator')
        self.state = 'home'
        self.machine = None

        self.data = []
        self.events = {
            'arrive_at_work': self.env.event()
        }

        self.env.process(self._home())
        self.env.process(self._monitor_issues())

    def assign_machine(self, machine):
        self.machine = machine
        return self

    def _get_time_until_next_work_arrival(self):
        ts = arrow.get(self.env.now).to('Europe/Helsinki')
        if ts.weekday() in (5, 6):
            days = 7 - ts.weekday()
        else:
            days = 0 if ts.hour < 8 else 1

        next_day = ts.day + days
        next_hour = 8
        next_minute = 0
        arrival = ts.replace(
            day=next_day, hour=next_hour, minute=next_minute)
        return arrival.timestamp() - self.env.now

    def _fix_issue(self, issue):
        if isinstance(issue, LowConsumableLevelIssue):
            # TODO: More complex, call repair person
            yield self.env.process(issue.consumable.fill_full())
            yield self.env.process(self.machine.clear_issue())
        else:
            raise UnknownIssue(f'How to fix {issue}?')

    def _monitor_issues(self):
        # TODO: React if no production output for a while
        while True:
            # Wait for issues...
            issue = yield self.machine.events['issue']

            # Issues can be seen only when at work
            if self.state == 'work':
                yield self.env.timeout(120)  # TODO: From distribution
            else:
                yield self.events['arrive_at_work']

            self.log(f'Observed issue "{issue}" and attempting to fix...')
            self.env.process(self._fix_issue(issue))

            # Wait until issue is cleared
            yield self.machine.events['issue_cleared']

    def _home(self):
        self.log('Chilling at home...')
        self.state = 'home'
        yield self.env.timeout(self._get_time_until_next_work_arrival())
        yield self.env.process(self._work())

    def _work(self):
        self.log('Working...')
        self.state = 'work'
        self.events['arrive_at_work'].succeed()
        self.events['arrive_at_work'] = self.env.event()

        self.env.process(self.machine.switch_on())
        yield (self.machine.events['switched_on']
               | self.machine.events['switched_idle'])
        # TODO: Program based on schedule
        # yield from self.machine.switch_program(1)
        yield self.env.timeout(self.hours(3.5))

        self.log('Preparing for lunch...')
        # TODO: Operator shouldn't switch off in case of an issue?
        #       OR some other mechanism to achieve the same
        self.env.process(self.machine.switch_off())
        yield self.machine.events['switched_off']
        lunch = self.env.process(self._lunch())
        yield lunch
        self.state = 'work'

        self.log('Continuing working...')
        self.env.process(self.machine.switch_on())
        yield (self.machine.events['switched_on']
               | self.machine.events['switched_idle'])
        # yield from self.machine.switch_program(1)
        yield self.env.timeout(self.hours(4))  # TODO: Randomize

        self.log('Preparing to go home...')
        self.env.process(self.machine.switch_off(force=False))
        yield self.machine.events['switched_off']
        self.env.process(self._home())

    def _lunch(self):
        self.log('Having lunch...')
        self.state = 'lunch'
        yield self.env.timeout(self.minutes(30))  # TODO: Randomize
