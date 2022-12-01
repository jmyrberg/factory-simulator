"""Models operator."""


from datetime import timedelta

import arrow
import simpy

from src.base import Base
from src.issues import LowConsumableLevelIssue, UnknownIssue
from src.utils import ignore_preempted, Monitor, with_resource_monitor


class Operator(Base):

    state = Monitor()
    issue_ongoing = Monitor()

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
        self.issue_ongoing = False
        self.can_leave = with_resource_monitor(
            simpy.PreemptiveResource(env),
            'can_leave', self
        )

        self.events = {
            'arrive_at_work': self.env.event()
        }

        self.env.process(self._home())
        self.env.process(self._monitor_issues())

    def assign_machine(self, machine):
        self.machine = machine
        return self

    def _get_time_until_next_work_arrival(self):
        # ts = self.now_dt.to(self.tz)
        # if ts.weekday() in ():
        #     days = 7 - ts.weekday()
        # else:
        #     days = 0 if ts.hour < 8 else 1

        return self.time_until_time('08:00')

    def _fix_issue(self, issue):
        if isinstance(issue, LowConsumableLevelIssue):
            # TODO: More complex, call repair person
            yield self.env.process(issue.consumable.fill_full())
            yield self.env.process(self.machine.clear_issue())
        else:
            raise UnknownIssue(f'How to fix {issue}?')

    def _monitor_issues(self):
        # TODO: React if no production output for a while
        # TODO: Have this process only running when at work
        yield self.events['arrive_at_work']
        while True:
            # Wait for issues...
            self.debug('Waiting for issues')
            issue = yield self.machine.events['issue_occurred']
            self.debug('Issue ongoing, but not noticed yet')
            self.issue_ongoing = True

            if self.state == 'work':
                self.debug('At work, will take time before issue noticed')
                yield self.env.timeout(10 * 60)  # TODO: From distribution
            else:
                self.debug(
                    'Will wait until arrival at work to notice the issue')
                yield self.events['arrive_at_work']

            with self.can_leave.request() as req:
                yield req
                self.log(f'Observed issue "{issue}" and attempting to fix...')
                self.env.process(self._fix_issue(issue))  # TODO: Call repairman

                # Wait until issue is cleared
                yield self.machine.events['issue_cleared']
                self.issue_ongoing = False

                # TODO: Switch to event from repairman
                if (len(self.can_leave.queue) == 0
                        and self.machine.state != 'production'):
                    self.debug('Restarting production manually')
                    self.env.process(self.machine.start_production())

    def _home(self):
        self.log('Chilling at home...')
        self.state = 'home'
        yield self.env.timeout(self._get_time_until_next_work_arrival())
        self.env.process(self._work())

    def _work(self):
        # TODO: Match schedule + operator actions (priority etc.)
        # Which overrides which?
        self.log('Working...')
        self.state = 'work'
        self.emit('arrive_at_work')
        self.env.process(self.machine.press_on())
        yield self.machine.events['switched_on']

        # Go lunch or home
        lunch = self.env.timeout(self.time_until_time('11:30'))
        home = self.env.timeout(self.time_until_time('17:00'))
        results = yield lunch | home
        self.debug('Lunch or home time')

        if lunch in results:
            self.env.process(self._lunch())
        elif home in results:
            with self.can_leave.request() as can_leave:
                yield can_leave
                self.env.process(self.machine.press_off())
                yield self.machine.events['switched_off']
                yield self.env.timeout(20 * 60)
                self.env.process(self._home())

    def _lunch(self):
        if self.time_passed_today('14:00'):
            self.debug('No lunch today, it seems :(')
            return

        with self.can_leave.request() as can_leave:
            self.debug('Waiting till can leave for lunch')
            lunch_time_over = self.env.timeout(self.time_until_time('14:00'))
            results = yield can_leave | lunch_time_over
            if lunch_time_over in results:
                self.debug('No lunch today, it seems :(')
                return

            self.env.process(self.machine.press_off())
            yield self.machine.events['switched_off']
            self.log('Having lunch...')
            self.state = 'lunch'
            yield self.env.timeout(self.minutes(30))  # TODO: Randomize
            self.env.process(self._work())
