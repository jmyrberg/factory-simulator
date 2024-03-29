"""Schedules."""


from datetime import datetime, timedelta
from typing import List

import simpy
from croniter import croniter

from src.simulator.base import Base
from src.simulator.utils import AttributeMonitor, MonitoredList


class Block(Base):

    is_active = AttributeMonitor()
    action = AttributeMonitor()

    def __init__(self, env, action=None, priority=0, name="block", uid=None):
        """Block defines an action to be run in a schedule.

        Args:
            action (tuple): Tuple of (action_func, args, kwargs). Assigned
            machine will be automatically passed within kwargs.
        """
        super().__init__(env, name=name, uid=uid)
        self.action = action
        self.priority = priority
        self.is_active = False
        self.deleted = False

        self.schedule = None
        self.events = {
            # Block related
            "start": self.env.event(),
            "started": self.env.event(),
            "stop": self.env.event(),
            "stopped": self.env.event(),
            # Action related
            "action_started": self.env.event(),
            "action_stopped": self.env.event(),
        }
        self.procs = {"run": self.env.process(self._run())}

    def delete(self):
        self.procs["run"].interrupt("Deleted")
        self.deleted = True

    def start(self):
        """Activate block from outside."""
        if self.is_active:
            self.warning("Tried to start an already active block")
        else:
            self.emit("start")
            self.is_active = True

    def stop(self):
        """Deactivate block from outside."""
        if self.is_active:
            self.emit("stop")
            self.is_active = False
        else:
            self.warning("Tried to stop already stopped block")

    def assign_schedule(self, schedule):
        self.schedule = schedule

    def assign_action(self, action):
        self.action = action

    def run_action(self):
        if self.action is not None:
            return self.action(block=self)
        else:
            self.warning("Tried to run action when action=None")

    def _run(self):
        while True:
            try:
                # Wait for start
                yield self.events["start"]

                # Start
                self.emit("started")
                self.is_active = True

                # Trigger block activation in schedule
                if self.schedule:
                    self.schedule.emit("block_started", self)
                else:
                    self.warning("No schedule to trigger")

                # Stop
                yield self.events["stop"]
                self.is_active = False

                # Trigger block stop in schedule
                self.emit("stopped")
                self.schedule.emit("block_finished", self)
            except simpy.Interrupt:  # = delete
                self.is_active = False
                # Trigger block stop in schedule
                self.schedule.emit("block_deleted", self)
                break


class CronBlock(Block):
    def __init__(
        self,
        env,
        cron,
        duration_hours,
        action=None,
        priority=0,
        name="cron-block",
        uid=None,
    ):
        """Block that starts on cron definition and lasts for duration."""
        super().__init__(
            env, action=action, priority=priority, name=name, uid=uid
        )
        self.cron = cron
        self.duration_hours = duration_hours
        self.next_start_dt = None
        self.next_end_dt = None

        self.env.process(self.start_cond())

    def start_cond(self):
        cron_iter = croniter(self.cron, self.now_dt.datetime)
        while True:
            self.next_start_dt = cron_iter.get_next(datetime)
            self.next_end_dt = self.next_start_dt + timedelta(
                hours=self.duration_hours, seconds=-1
            )
            timeout = self.time_until(self.next_start_dt)
            self.env.process(self.end_cond())

            self.info(
                "Cron scheduled for "
                f'{self.next_start_dt.strftime("%Y-%m-%d %H:%M:%S")} - '
                f'{self.next_end_dt.strftime("%Y-%m-%d %H:%M:%S")}'
            )

            yield self.env.timeout(timeout)
            self.start()

    def end_cond(self):
        if self.next_end_dt is None:
            raise ValueError("End time cannot be determined")

        yield self.env.timeout(self.time_until(self.next_end_dt))
        self.stop()


class Schedule(Base):

    active_block = AttributeMonitor()

    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        blocks: List[Block] = None,
        name: str = "schedule",
        uid: str | None = None,
    ):
        """Run actions when scheduled.

        Args:
            env: Simpy environment.
            blocks (optional): Blocks belonging to the schedule. Defaults to
                None.
            name (optional): Name of the schedule. Defaults to "schedule".
            uid (optional): Unique ID for the schedule. Defaults to None.
        """
        super().__init__(env, name=name, uid=uid)
        self.blocks = blocks
        for block in self.blocks:
            block.assign_schedule(self)

        self.active_block = None
        self.active_blocks = self.with_monitor(
            MonitoredList(),
            post=[("n_blocks", lambda x: len(x))],
            name="active_blocks",
        )
        self.procs = {
            "on_block_start": self.env.process(self._on_block_start()),
            "on_block_finish": self.env.process(self._on_block_finished()),
        }
        self.events = {
            "block_started": self.env.event(),
            "block_finished": self.env.event(),
            "block_deleted": self.env.event(),
        }

    def _on_block_start(self):
        while True:
            block = yield self.events["block_started"]

            # Add to active blocks
            if block in self.active_blocks:
                self.warning(
                    "Starting block already in active blocks, is this on "
                    "purpose?"
                )
            else:
                self.active_blocks.append(block)

            # Check if needs to change and run the active block
            needs_to_run = True
            if self.active_block is None:
                self.active_block = block
            elif block.priority <= self.active_block.priority:
                if self.active_block.is_active:
                    self.warning(
                        "Stopping currently active block "
                        f'"{self.active_block}" due to priorities'
                    )
                    self.active_block.stop()
                self.active_block = block
            else:
                self.warning(
                    f'Will not set new block "{block}" as active due to '
                    "priorities"
                )
                needs_to_run = False

            if needs_to_run:
                self.procs["action"] = self.env.process(
                    self.active_block.run_action()
                )

    def _on_block_finished(self):
        while True:
            block = yield self.events["block_finished"]
            if block in self.active_blocks:
                self.active_blocks.remove(block)
            else:
                self.warning(
                    f'Block "{block}" finished, but not in active blocks: '
                    f"{self.active_blocks}"
                )

            if len(self.active_blocks) == 0:
                self.active_block = None


class OperatingSchedule(Schedule):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        blocks: List[Block] = None,
        name: str = "operating-schedule",
        uid: str | None = None,
    ):
        """Controls the "program" -attribute of a machine.

        Args:
            env: Simpy environment.
            blocks (optional): Blocks belonging to the schedule. Defaults to
                None.
            name (optional): Name of the operating schedule. Defaults to
                "operating-schedule".
            uid (optional): Unique ID for the operating schedule. Defaults to
                None.
        """
        super().__init__(env, blocks=blocks, name=name, uid=uid)

        self.machine = None

        self.procs = {
            "on_machine_start": self.env.process(self._on_machine_start())
        }
        self.events["machine_assigned"] = self.env.event()

    def assign_machine(self, machine):
        self.machine = machine
        self.emit("machine_assigned")
        yield self.env.timeout(0)

    def _on_machine_start(self):
        while True:
            if self.machine is None:
                yield self.events["machine_assigned"]

            if self.machine is not None:
                yield self.machine.events["switched_on_from_off"]

            # NOTE: Not tested if machine unassigned?

            if self.machine and self.active_block:
                self.debug(
                    f'Running block "{self.active_block}" at machine start'
                )
                self.procs["action"] = self.env.process(
                    self.active_block.run_action()
                )
