"""Models operator."""


from datetime import timedelta

import arrow
import simpy

from src.base import Base
from src.causes import WorkStoppedCause
from src.issues import LowContainerLevelIssue, UnknownIssue
from src.utils import ignore_causes, Monitor, with_resource_monitor


class Operator(Base):

    state = Monitor()
    issue_ongoing = Monitor()

    def __init__(self, env, machine=None, name='operator'):
        """Models an operator at the factory.

        Basic cycle:
            1) Go to work in the morning, if it's not weekend
            2) Operate/monitor the machine
            3) Go to lunch
            4) Operate/monitor the machine
            5) Go home
        """
        super().__init__(env, name=name)
        self.state = 'home'
        self.machine = machine

        # Internal
        self.issue_ongoing = False
        self.had_lunch = False
        self.can_leave = with_resource_monitor(
            simpy.PreemptiveResource(env),
            'can_leave', self
        )

        self.events = {
            'home': self.env.event(),
            'work_started': self.env.event(),
            'work_stopped': self.env.event()
        }
        self.procs = {
            'home': self.env.process(self._home()),
            'on_work_started': self.env.process(self._on_work_started()),
            'on_work_stopped': self.env.process(self._on_work_stopped())
        }

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
        if isinstance(issue, LowContainerLevelIssue):
            # TODO: More complex, call repair person
            for container in issue.containers:
                # TODO: Dont fill all?
                yield self.env.process(container.put_full())
            yield self.env.process(self.machine.clear_issue())
        else:
            raise UnknownIssue(f'No idea how to fix "{issue}"? :(')

    def _on_work_started(self):
        while True:
            yield self.events['work_started']
            for proc in [
                'monitor_issues',
                'monitor_production',
                'monitor_home',
                'monitor_lunch'
            ]:
                func = getattr(self, f'_{proc}')
                self.procs[proc] = self.env.process(func())

    def _on_work_stopped(self):
        while True:
            yield self.events['work_stopped']
            for proc in [
                'monitor_issues',
                'monitor_production',
                'monitor_home',
                'monitor_lunch'
            ]:
                if self.procs[proc].is_alive:
                    cause = WorkStoppedCause(proc)
                    self.procs[proc].interrupt(cause)

    @ignore_causes(WorkStoppedCause)
    def _monitor_issues(self):
        # TODO: React if no production output for a while
        # TODO: Have this process only running when at work
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

    @ignore_causes(WorkStoppedCause)
    def _monitor_lunch(self):
        latest_at = '14:30'
        desired_at = '11:30'

        if self.had_lunch:
            return

        while True:
            if not self.time_passed_today(desired_at):
                yield self.env.timeout(self.time_until_time(desired_at))

            leave_latest = self.env.timeout(self.time_until_time(latest_at))
            with self.can_leave.request() as can_leave:
                res = yield can_leave | leave_latest

                if leave_latest in res:
                    self.debug('No lunch today, it seems :(')
                else:
                    self.info('Having lunch')
                    self.env.process(self.machine.press_off())
                    yield self.machine.events['switched_off']
                    self.env.process(self._lunch())
                    self.emit('work_stopped')

                break

    @ignore_causes(WorkStoppedCause)
    def _monitor_home(self):
        latest_at = '22:00'
        desired_at = '17:00'
        while True:
            if not self.time_passed_today(desired_at):
                yield self.env.timeout(self.time_until_time(desired_at))

            latest_passed = self.time_passed_today(latest_at)
            priority = -10 if latest_passed else 0
            with self.can_leave.request(priority) as can_leave:
                yield can_leave

                # Switch off and go home
                self.env.process(self.machine.press_off(force=latest_passed))
                yield self.machine.events['switched_off']
                self.env.process(self._home())
                self.emit('work_stopped')

                break

    @ignore_causes(WorkStoppedCause)
    def _monitor_production(self):
        while True:
            if self.machine.state == 'off':
                self.env.process(self.machine.press_on())
                switched_on = self.machine.events['switched_on']
                try_again = self.env.timeout(60)
                res = yield switched_on | try_again
                if try_again in res:
                    self.info('Trying to switch on again...')

            yield self.events['work_started']

            # TODO: Add different kinds of checks
            # - Production output normal?
            # - Time since machine on / off / ...

    def _home(self):
        self.log('Chilling at home...')
        self.state = 'home'
        yield self.env.timeout(self._get_time_until_next_work_arrival())
        self.had_lunch = False
        self.env.process(self._work())

    def _work(self):
        # TODO: Refactor whole operator (intentions instead of one func.)
        self.log('Working...')
        self.state = 'work'
        self.emit('work_started')
        yield self.env.timeout(0)

    def _lunch(self):
        self.log('Having lunch...')
        self.state = 'lunch'
        yield self.env.timeout(self.minutes(30))  # TODO: Randomize
        self.had_lunch = True
        self.env.process(self._work())
