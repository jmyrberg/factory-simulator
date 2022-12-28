"""Models operator."""


import simpy

from src.simulator.base import Base
from src.simulator.causes import WorkStoppedCause
from src.simulator.issues import LowContainerLevelIssue, UnknownIssue
from src.simulator.utils import AttributeMonitor, ignore_causes


class Operator(Base):

    state = AttributeMonitor()
    issue_ongoing = AttributeMonitor()
    had_lunch = AttributeMonitor()

    def __init__(self, env, machine=None, name="operator"):
        """Models an operator at the factory.

        Basic cycle:
            1) Go to work in the morning, if it's not weekend
            2) Operate/monitor the machine
            3) Go to lunch
            4) Operate/monitor the machine
            5) Go home
        """
        super().__init__(env, name=name)
        self.machine = machine

        # Constants
        self.workdays = [0, 1, 2, 3, 4, 5, 6]
        self.work_start_desired_at = "08:00"
        self.work_end_desired_at = "17:00"
        self.work_end_latest_at = "22:00"
        self.lunch_desired_at = "11:30"
        self.lunch_latest_at = "14:00"
        self.lunch_duration_mins = 30

        # Internal states
        self.state = "home"
        self.issue_ongoing = False
        self.had_lunch = False

        # Internal resources
        self.attention = self.with_monitor(
            simpy.PreemptiveResource(env), name="attention"
        )

        # Events and processes
        self.events = {
            "home": self.env.event(),
            "work_started": self.env.event(),
            "work_stopped": self.env.event(),
        }
        self.procs = {
            "home": self.env.process(self._home()),
            "on_work_started": self.env.process(self._on_work_started()),
            "on_work_stopped": self.env.process(self._on_work_stopped()),
        }

    def assign_machine(self, machine):
        self.machine = machine
        return self

    def _get_time_until_next_work_arrival(self):
        next_arrival = self.now_dt.shift(
            days=self.days_until(self.now_dt.weekday()),
            seconds=self.time_until_time(self.work_start_desired_at),
        )
        self.debug(f"Next work arrival: {next_arrival.strftime(self.dtfmt)}")
        return self.time_until(next_arrival)

    def _on_work_started(self):
        """Run processes when at work."""
        while True:
            yield self.events["work_started"]
            for proc in [
                "monitor_issues",
                "monitor_production",
                "monitor_home",
                "monitor_lunch",
            ]:
                func = getattr(self, f"_{proc}")
                self.procs[proc] = self.env.process(func())

    def _on_work_stopped(self):
        """Stop processes when out of factory."""
        while True:
            yield self.events["work_stopped"]
            for proc in [
                "monitor_issues",
                "monitor_production",
                "monitor_home",
                "monitor_lunch",
            ]:
                if self.procs[proc].is_alive:
                    cause = WorkStoppedCause(proc)
                    self.procs[proc].interrupt(cause)

    def _fix_issue(self, issue):
        if isinstance(issue, LowContainerLevelIssue):
            for container in issue.containers:
                yield self.env.process(container.put_full())
            yield self.env.process(self.machine.clear_issue())
        else:
            raise UnknownIssue(f'No idea how to fix "{issue}"? :(')

    @ignore_causes(WorkStoppedCause)
    def _monitor_issues(self):
        # TODO: React if no production output for a while
        # TODO: Have this process only running when at work
        while True:
            self.debug("Waiting for issues...")
            issue = yield self.machine.events["issue_occurred"]
            self.debug(f"Issue {issue} ongoing, but not noticed yet")
            self.issue_ongoing = True

            yield self.env.timeout(10 * 60)  # TODO: From distribution

            # Cannot leave when issue ongoing (unless interrupted elsewhere)
            with self.attention.request() as attention:
                yield attention
                self.debug('Requested "attention" from "monitor_issues"')

                self.info(f'Observed issue "{issue}" and attempting to fix...')
                self.env.process(self._fix_issue(issue))

                # Wait until issue is cleared
                yield self.machine.events["issue_cleared"]
                self.issue_ongoing = False

                # Continue, if not going to leave after fix
                if (
                    len(self.attention.queue) == 0
                    and self.machine.state != "production"
                ):
                    self.info("Restarting production manually after issue")
                    self.env.process(self.machine.start_production())

            self.debug('Released "attention"')

    @ignore_causes(WorkStoppedCause)
    def _monitor_lunch(self):
        if self.had_lunch:
            self.debug("Had lunch today already, returning")
            return

        while True:
            if not self.time_passed_today(self.lunch_desired_at):
                yield self.env.timeout(
                    self.time_until_time(self.lunch_desired_at)
                )

            leave_latest = self.env.timeout(
                self.time_until_time(self.lunch_latest_at)
            )
            with self.attention.request() as attention:
                res = yield attention | leave_latest
                self.debug('Requested "attention" from "monitor_lunch"')

                if leave_latest in res:
                    self.info("No lunch today, it seems :(")
                else:
                    self.debug("Planning to have lunch")
                    self.env.process(self.machine.press_off())
                    yield self.machine.events["switched_off"]
                    self.env.process(self._lunch())
                    self.emit("work_stopped")

                break

    @ignore_causes(WorkStoppedCause)
    def _monitor_home(self):
        while True:
            if not self.time_passed_today(self.work_end_desired_at):
                yield self.env.timeout(
                    self.time_until_time(self.work_end_desired_at)
                )

            latest_passed = self.time_passed_today(self.work_end_latest_at)
            if latest_passed:
                self.info(
                    "Latest work end time passed, going home no matter what"
                )

            priority = -10 if latest_passed else 0
            with self.attention.request(priority) as attention:
                yield attention
                self.debug('Requested "attention" from "monitor_home"')

                # Switch off and go home
                self.debug("Planning to go home")
                self.env.process(self.machine.press_off(force=latest_passed))
                yield self.machine.events["switched_off"]
                self.env.process(self._home())
                self.emit("work_stopped")

                break

    @ignore_causes(WorkStoppedCause)
    def _monitor_production(self):
        while True:
            if self.issue_ongoing:  # Separate monitoring for this
                yield self.machine.events["issue_cleared"]

            if self.machine.state == "off" and not self.issue_ongoing:
                self.env.process(self.machine.press_on())
                yield self.machine.events["switched_on"]

            # Wait for next events
            work_started = self.events["work_started"]
            issue_occurred = self.machine.events["issue_occurred"]
            issue_cleared = self.machine.events["issue_cleared"]
            yield work_started | issue_occurred | issue_cleared

            # TODO: Add different kinds of checks
            # - Production output normal?
            # - Time since machine on / off / ...

    def _home(self):
        self.info("Chilling at home...")
        self.state = "home"
        yield self.env.timeout(self._get_time_until_next_work_arrival())
        self.had_lunch = False
        self.env.process(self._work())

    def _work(self):
        self.info("Working...")
        self.state = "work"
        self.emit("work_started")
        yield self.env.timeout(0)

    def _lunch(self):
        self.info("Having lunch...")
        self.state = "lunch"
        yield self.env.timeout(self.minutes(self.lunch_duration_mins))
        self.had_lunch = True
        self.env.process(self._work())
