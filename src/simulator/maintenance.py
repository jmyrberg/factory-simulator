"""Machine maintenance."""


import simpy

from src.simulator.base import Base
from src.simulator.issues import OtherCustomerIssue, ScheduledMaintenanceIssue


class Maintenance(Base):
    def __init__(self, env, workers=2, name="maintenance"):
        super().__init__(env, name=name)
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
        if priority is None and hasattr(issue, "priority"):
            priority = issue.priority
        else:
            priority = 5
        issue = simpy.PriorityItem(priority, item=issue)
        yield self.wnorm(self.minutes(5))
        self.issues.put(issue)
        self.emit("added_issue")

    def _fix_issue(self, issue):
        if isinstance(issue, ScheduledMaintenanceIssue):
            duration = issue.duration
            machine = issue.machine

            # Turn off
            self.env.process(machine.press_off())
            yield machine.events["switched_off"]

            with machine.ui.request(-99) as ui:
                yield ui
                with machine.execute.request(-99) as executor:
                    yield executor

                    real_duration = duration + self.minutes(self.iuni(-60, 60))
                    yield self.wnorm(real_duration)

            self.env.process(machine.press_on())
            yield machine.events["switched_on"]

            # TODO: Implement maintenance log machine side
            # machine.log_maintenance(start_time)
        else:
            self.warning(f"Unknown issue: {issue}")
            yield self.wnorm(self.hours(self.iuni(3, 6)))

    def repair(self):
        while True:
            issue = yield self.issues.get()
            item = issue.item
            with self.workers.request(item.priority) as wait_worker:
                yield wait_worker
                self.emit("fixing_issue")
                yield self.env.process(self._fix_issue(item))
                self.emit("fixed_issue")

    def issue_producer(self):
        while True:
            next_issue_in = 60 * 60 * self.iuni(12, 48)
            priority = self.iuni(3, 5, weights=[0.8, 0.1, 0.1])
            yield self.wnorm(next_issue_in)
            self.add_issue(OtherCustomerIssue(), priority=priority)
