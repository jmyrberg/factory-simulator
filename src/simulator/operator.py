"""Models operator."""


import simpy

from src.simulator.base import Base
from src.simulator.causes import WorkStoppedCause
from src.simulator.containers import MaterialContainer
from src.simulator.issues import (
    LowContainerLevelIssue,
    OverheatIssue,
    PartBrokenIssue,
    UnknownIssue,
)
from src.simulator.machine import Machine
from src.simulator.utils import AttributeMonitor, ignore_causes


class Operator(Base):

    state = AttributeMonitor()
    issue_ongoing = AttributeMonitor()
    had_lunch = AttributeMonitor()

    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        machine: Machine | None = None,
        name: str = "operator",
        uid: str | None = None,
    ):
        """Models an operator at the factory.

        Args:
            env: Simpy environment.
            name (optional): Name of the material. Defaults to "material".
            uid (optional): Unique ID for the material. Defaults to None.

        Basic cycle:
            1) Go to work in the morning, if it's not weekend
            2) Operate/monitor the machine
            3) Go to lunch
            4) Operate/monitor the machine
            5) Go home

        TODO: Operator adds quite much complexity with little value - remove!
        """
        super().__init__(env, name=name, uid=uid)
        self.machine = machine

        # Constants
        self.workdays = [0, 1, 2, 3, 4, 5, 6]
        self.work_start_desired_at = "07:30"
        self.work_end_desired_at = "15:30"
        self.work_end_latest_at = "21:00"
        self.lunch_desired_at = "11:30"
        self.lunch_latest_at = "14:00"
        self.lunch_duration_mins = 30

        # Internal states
        self.state = "home"
        self.issue_ongoing = False
        self.issue = None
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
            self.debug("Fixing low container level issue")
            for container in issue.containers:
                if isinstance(container, MaterialContainer):
                    yield self.env.process(
                        container.put_full(
                            pct=0.1,
                            quality=(0.5, 0.1),
                        )
                    )
                else:
                    yield self.env.process(container.put_full(pct=0.1))
            yield self.env.process(self.machine.clear_issue())
        elif isinstance(issue, PartBrokenIssue):
            if issue.needs_maintenance:
                self.debug("Adding part broken issue to maintenance team")
                yield from self.machine.maintenance.add_issue(
                    issue, priority=issue.priority
                )
            else:
                self.info("Fixing part broken issue")
                duration = issue.difficulty * self.hours(1)
                yield self.wnorm(0.9 * duration, 1.1 * duration)
                yield self.env.process(self.machine.clear_issue())
        elif isinstance(issue, OverheatIssue):
            wait_until_temp = 0.75 * issue.limit
            self.debug(f"Waiting until temperature below {wait_until_temp}")
            while True:  # Wait until low enough temperature
                yield issue.sensor.events["temperature_changed"]
                if issue.sensor.value < wait_until_temp:
                    break
            yield self.env.process(self.machine.clear_issue())
        else:
            raise UnknownIssue(f'No idea how to fix "{issue}"? :(')

    @ignore_causes(WorkStoppedCause)
    def _monitor_issues(self):
        # TODO: React if no production output for a while
        # TODO: Have this process only running when at work
        while True:
            self.debug("Waiting for issues...")
            if not self.issue_ongoing:
                self.issue = yield self.machine.events["issue_occurred"]
            self.debug(f"Issue {self.issue} ongoing, but not noticed yet")
            self.issue_ongoing = True

            yield self.wnorm(10 * 60)  # TODO: From distribution

            # Cannot leave when issue ongoing (unless interrupted elsewhere)
            with self.attention.request() as attention:
                yield attention
                self.debug('Requested "attention" from "monitor_issues"')

                self.info(
                    f'Observed issue "{self.issue}" and attempting to fix...'
                )
                self.env.process(self._fix_issue(self.issue))

                # Wait until issue is cleared
                yield self.machine.events["issue_cleared"]
                self.issue_ongoing = False
                self.issue = None

            self.debug('Released "attention"')

    @ignore_causes(WorkStoppedCause)
    def _monitor_lunch(self):
        if self.had_lunch:
            self.debug("Had lunch today already, returning")
            return

        while True:
            if not self.time_passed_today(self.lunch_desired_at):
                yield self.wnorm(self.time_until_time(self.lunch_desired_at))

            leave_latest = self.wnorm(
                self.time_until_time(self.lunch_latest_at)
            )
            with self.attention.request() as attention:
                res = yield attention | leave_latest
                self.debug('Requested "attention" from "monitor_lunch"')

                if leave_latest in res:
                    self.info("No lunch today, it seems :(")
                else:
                    self.debug("Planning to have lunch")
                    self.env.process(self.machine.press_off(force=False))

                    timeout = self.env.timeout(120)
                    switched_off = self.machine.events["switched_off"]
                    res = yield timeout | switched_off
                    if switched_off in res:
                        self.env.process(self._lunch())
                        self.emit("work_stopped")
                        break

    @ignore_causes(WorkStoppedCause)
    def _monitor_home(self):
        while True:
            if not self.time_passed_today(self.work_end_desired_at):
                desired_at = self.time_until_time(self.work_end_desired_at)
                early_mins = 45 if self.dow >= 4 else 5
                yield self.wnorm(
                    low=desired_at - self.minutes(early_mins),
                    high=desired_at + self.minutes(45),
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

                timeout = self.env.timeout(120)
                switched_off = self.machine.events["switched_off"]
                res = yield timeout | switched_off
                if switched_off in res:
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
        next_arrival = self._get_time_until_next_work_arrival()
        yield self.wnorm(
            low=next_arrival,
            high=next_arrival + self.minutes(15),
        )
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
        yield self.wnorm(
            self.minutes(self.lunch_duration_mins - 5),
            self.minutes(self.lunch_duration_mins + 15),
        )
        self.had_lunch = True
        self.env.process(self._work())
