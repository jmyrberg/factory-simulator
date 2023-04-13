"""Machine maintenance."""


import simpy

from src.simulator.base import Base
from src.simulator.issues import (
    OtherCustomerIssue,
    PartBrokenIssue,
    ScheduledMaintenanceIssue,
)


class Maintenance(Base):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        workers: int = 2,
        name: str = "maintenance",
        uid: str | None = None,
    ):
        """Maintenance service.

        Args:
            env: Simpy environment.
            workers (optional): Number of workers in the worker team. Defaults
                to 2.
            name (optional): Name of the machine. Defaults to "machine".
            uid (optional): Unique ID of the object. Defaults to None.
        """
        super().__init__(env, name=name, uid=uid)
        self.issues = self.with_monitor(
            simpy.PriorityStore(env), name="issues"
        )
        self.workers = self.with_monitor(
            simpy.PreemptiveResource(env=env, capacity=workers), name="workers"
        )

        self.events = {
            "added_issue": self.env.event(),
            "fixing_issue": self.env.event(),
            "fixed_issue": self.env.event(),
        }
        self.procs = {
            "repair": self.env.process(self.repair()),
            "issue_producer": self.env.process(self.issue_producer()),
        }

    def add_issue(self, issue, priority=None):
        """Add issue to maintenance team backlog."""
        if priority is None and hasattr(issue, "priority"):
            priority = issue.priority
        else:
            priority = 5

        if issue in self.issues.items:
            self.warning(f"Issue {issue} already in issues, ignoring")
            yield self.wnorm(self.minutes(1))
            return
        else:
            yield self.wnorm(self.minutes(5))
            self.issues.put(simpy.PriorityItem(priority, item=issue))

            self.emit("added_issue")

    def _fix_issue(self, issue):
        """Internal process to fix an issue."""
        if isinstance(issue, ScheduledMaintenanceIssue):
            duration = issue.duration
            machine = issue.machine

            # Turn off no matter what
            self.env.process(
                machine.press_off(force=True)
            )  # Should take executor
            yield machine.events["switched_off"]

            with machine.ui.request(-99) as ui:
                yield ui
                self.debug("Locked UI")
                with machine.execute.request(-99) as executor:
                    yield executor
                    self.debug("Locked executor")

                    real_duration = duration + self.minutes(self.iuni(-60, 60))
                    self.debug(f"Waiting {real_duration} seconds")
                    yield self.wnorm(real_duration)

        elif isinstance(issue, PartBrokenIssue):
            duration = self.hours(issue.difficulty)
            machine = issue.machine
            yield self.wnorm(0.9 * duration, 1.1 * duration)

            self.env.process(machine.clear_issue())
            yield machine.events["issue_cleared"]
        else:
            self.warning(f"Unknown issue: {issue}")
            yield self.wnorm(self.hours(self.iuni(3, 6)))

        # TODO: Implement maintenance log machine side
        # machine.log_maintenance(start_time)

    def repair(self):
        """Repair process."""
        while True:
            issue = yield self.issues.get()
            item = issue.item
            with self.workers.request(item.priority) as wait_worker:
                yield wait_worker
                self.emit("fixing_issue")
                yield self.env.process(self._fix_issue(item))
                self.emit("fixed_issue")

    def issue_producer(self):
        """Process that produces random issues for the team."""
        while True:
            next_issue_in = 60 * 60 * self.iuni(12, 48)
            priority = self.iuni(3, 5, weights=[0.8, 0.1, 0.1])
            yield self.wnorm(next_issue_in)
            self.add_issue(OtherCustomerIssue(), priority=priority)
