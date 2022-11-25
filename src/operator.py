"""Models operator."""


from datetime import timedelta

import arrow
import simpy

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
        ts = self.now_dt.to(self.tz)
        if ts.weekday() in ():
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
            issue = yield self.machine.events['issue_occurred']
            self.issue_ongoing = True
      
            if self.state == 'work':
                yield self.env.timeout(120)  # TODO: From distribution
            else:
                yield self.events['arrive_at_work']

            self.log(f'Observed issue "{issue}" and attempting to fix...')
            self.env.process(self._fix_issue(issue))  # TODO: Call repairman

            # Wait until issue is cleared
            yield self.machine.events['issue_cleared']

            # TODO: Switch to event from repairman
            if self.machine.state != 'production':
                self.debug('Restarting production manually')
                self.env.process(self.machine.start_production())

    def _home(self):
        self.log('Chilling at home...')
        self.state = 'home'
        yield self.env.timeout(self._get_time_until_next_work_arrival())
        yield self.env.process(self._work())

    def _start_production(self):
        if self.machine.state != 'on':
            self.env.process(self.machine.press_on())
            yield self.machine.events['switched_on']
        if self.machine.state == 'on':
            self.env.process(self.machine.start_production())
            yield self.machine.events['switched_production']

    def _stop_production(self):
        if self.machine.state != 'off':
            self.env.process(self.machine.press_off(max_wait=120))
            yield self.machine.events['switched_off']

    def _work(self):
        self.log('Working...')
        self.state = 'work'
        self._trigger_event('arrive_at_work')
        yield from self._start_production()

        # Go lunch or home
        lunch = self.env.timeout(self.time_until_time('11:30'))
        home = self.env.timeout(self.time_until_time('17:00'))
        results = yield lunch | home
        if lunch in results:
            self.env.process(self._lunch())
        elif home in results:
            self.env.process(
                self.machine.press_off(max_wait=4 * 60 * 60))
            yield self.machine.events['switched_off']
            self.env.process(self._home())

    def _lunch(self):
        yield from self._stop_production()
        self.log('Having lunch...')
        self.state = 'lunch'
        yield self.env.timeout(self.minutes(30))  # TODO: Randomize
        self.env.process(self._work())
