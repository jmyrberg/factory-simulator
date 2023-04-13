"""Machine in a factory."""


from typing import List, Tuple

import numpy as np
import simpy

from src.simulator.base import Base
from src.simulator.causes import (
    AutomatedStopProductionCause,
    BaseCause,
    ManualStopProductionCause,
    ManualSwitchOffCause,
    ProgramSwitchCause,
    UnknownCause,
)
from src.simulator.containers import ContainerType
from src.simulator.issues import PartBrokenIssue, ProductionIssue
from src.simulator.maintenance import Maintenance
from src.simulator.program import Program
from src.simulator.schedules import OperatingSchedule
from src.simulator.sensors import MachineTemperatureSensor
from src.simulator.utils import AttributeMonitor, ignore_causes


class Machine(Base):

    state = AttributeMonitor()
    program = AttributeMonitor()
    production_interruption_ongoing = AttributeMonitor()
    production_interrupt_code = AttributeMonitor()
    error_code = AttributeMonitor()
    temperature = AttributeMonitor("numerical")
    is_planned_operating_time = AttributeMonitor()

    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        containers: List[ContainerType] | None = None,
        schedule: OperatingSchedule | None = None,
        programs: List[Program] | None = None,
        default_program: Program | None = None,
        maintenance: Maintenance | None = None,
        part_fail_freq_days: Tuple[int, int] = (7, 31),
        name: str = "machine",
        uid: str | None = None,
    ) -> None:
        """Machine in a factory.

        Args:
            env: Simpy environment.
            containers (optional): Containers attached to the machine. Defaults
                to None.
            schedule (optional): Operating schedule of the machine. Defaults to
                None.
            programs (optional): Available programs on the machine. Defaults to
                None.
            default_program (optional): Default program of the machine.
                Defaults to first program in `programs`.
            maintenance (optional): Maintenance team for the machine. Defaults
                to None.
            part_fail_freq_days (optional): 95% confidence intervals that a
                part failure will happen between (min, max) -days.
            name (optional): Name of the machine. Defaults to "machine".
            uid (optional): Unique ID of the object. Defaults to None.

        Possible states: ["off", "on", "production", "error"]
        """
        super().__init__(env, name=name, uid=uid)
        self.schedule = schedule
        self.containers = containers or []
        self.programs = programs
        self.program = default_program or self.programs[0]
        self.maintenance = maintenance
        self.part_fail_freq_days = part_fail_freq_days

        # Internal states
        self.ui = self.with_monitor(simpy.PreemptiveResource(env), name="ui")
        self.execute = self.with_monitor(
            simpy.PreemptiveResource(env), name="executor"
        )
        self.state = "off"
        self.states = ["off", "on", "production", "error"]
        self.production_interruption_ongoing = False
        self.production_interrupt_code = 0
        self.error_code = 0
        self.is_planned_operating_time = False  # Controlled by actions
        self.consumption = self.with_monitor(  # Updated within program
            {},
            post=[
                (uid, lambda x: x[uid] if uid in x else 0)
                for uid in set(
                    [
                        uid
                        for program in self.programs
                        for uid in (
                            program.get_material_uids()
                            + program.get_consumable_uids()
                        )
                    ]
                )
            ],
            name="consumption",
        )
        self.material_id = self.with_monitor(
            {},
            post=[
                (uid, lambda x: x[uid] if uid in x else 0)
                for uid in set(
                    [
                        uid
                        for program in self.programs
                        for uid in program.get_material_uids()
                    ]
                )
            ],
            name="material_id",
        )
        self.latest_batch_id = self.with_monitor(
            {},
            post=[
                (uid, lambda x: x[uid] if uid in x else "null")
                for uid in set(
                    [
                        uid
                        for program in self.programs
                        for uid in program.get_material_uids()
                    ]
                )
            ],
            name="latest_batch_id",
        )
        self.sensors = [
            MachineTemperatureSensor(
                env, self, uid=f"{self.uid}-temperature-sensor"
            ),
        ]
        self.events = {
            # Program
            "switching_program": self.env.event(),
            "switched_program": self.env.event(),
            # User
            "on_button_pressed": self.env.event(),
            "off_button_pressed": self.env.event(),
            "start_buttion_pressed": self.env.event(),
            "stop_button_pressed": self.env.event(),
            "killswitch_pressed": self.env.event(),
            # Internal state change
            "state_change": self.env.event(),
            # Off
            "switching_off": self.env.event(),
            "switched_off": self.env.event(),
            # On
            "switching_on": self.env.event(),
            "switched_on": self.env.event(),
            "switched_on_from_off": self.env.event(),
            # Production
            "switching_production": self.env.event(),
            "switched_production": self.env.event(),
            "production_started": self.env.event(),
            "production_stopped": self.env.event(),
            "production_stopped_from_error": self.env.event(),
            "production_interrupted": self.env.event(),
            # Error
            "switching_error": self.env.event(),
            "switched_error": self.env.event(),
            "issue_occurred": self.env.event(),
            "issue_cleared": self.env.event(),
            "clearing_issue": self.env.event(),
            # Schedule
            "switching_program_automatically": self.env.event(),
            "switched_program_automatically": self.env.event(),
            # Other
            "temperature_change": self.env.event(),
        }
        self.procs = {
            "init": self.env.process(self._init()),
            "machine_break": self.env.process(self._machine_break_proc()),
        }

    def _init(self):
        if self.schedule is not None:
            yield self.env.process(self.schedule.assign_machine(self))

    def _machine_break_proc(self):
        parts = [
            {
                "part_name": "part1",
                "needs_maintenance": False,
                "priority": 5,
                "difficulty": 1,
                "code": 200 + 1,
                "weight": 10,
            },
            {
                "part_name": "part2",
                "needs_maintenance": False,
                "priority": 5,
                "difficulty": 2,
                "code": 200 + 2,
                "weight": 8,
            },
            {
                "part_name": "part3",
                "needs_maintenance": True,
                "priority": 0,
                "difficulty": 4,
                "code": 200 + 3,
                "weight": 6,
            },
            {
                "part_name": "part4",
                "needs_maintenance": True,
                "priority": 0,
                "difficulty": 8,
                "code": 200 + 4,
                "weight": 4,
            },
        ]
        weights = np.array(
            [part.pop("weight") for part in parts], dtype="float"
        )
        weights /= weights.sum()

        yield self.env.timeout(0)
        while True:
            min_days, max_days = self.part_fail_freq_days
            yield self.wnorm(self.days(min_days), self.days(max_days))
            part = self.choice(parts, p=weights)
            issue = PartBrokenIssue(machine=self, **part)

            if self.state == "off":
                yield self.events["switched_on"]
                yield self.wjitter()

            self.warning(f"Machine part broken: {issue}")
            yield self.env.process(self._switch_error(issue))

    @ignore_causes()
    def _switch_on(
        self, require_executor=True, priority=0, max_wait=0, cause=None
    ):
        """Change machine state to "on".

        State changes:
        off        -> on: Yes
        on         -> on: No
        production -> on: Yes
        error      -> on: No

        Possible actions:
        - Change settings, e.g. program or schedule
        """
        yield self.wjitter()

        if self.state == "on":
            self.warning(f'Cant go from state "{self.state}" to "on"')
            self.emit("switched_on")
            return
        elif self.state not in ["off", "production"]:
            self.warning(f'Cant go from state "{self.state}" to "on"')

        with self.execute.request(priority=priority) as executor:
            results = yield executor | self.env.timeout(max_wait)
            if executor not in results:
                self.debug('Execution ongoing, will not try to go "on"')
                return

            self.debug('Locked executor at "switch_on"')

            # Turn machine on
            if self.state == "off":
                self.emit("switching_on")
                yield self.wnorm(30, 60)
                self.state = "on"
                self.emit("switched_on")
                self.emit("switched_on_from_off")
            elif self.state == "production":
                self.emit("switching_on")

                # Stop production gracefully
                if not self.production_interruption_ongoing:
                    if cause is None:
                        cause = ManualSwitchOffCause(force=False)
                    self.env.process(
                        self._interrupt_production(
                            cause, require_executor=False
                        )
                    )

                self.debug('Waiting for production stopped at "switch_on"')
                yield self.events["production_stopped"]

                yield self.wjitter()
                self.state = "on"
                self.emit("switched_on")

        self.debug('Released executor at "switch_on"')

    def press_on(self, priority=-10):
        yield self.wnorm(1, 3)
        self.emit("on_button_pressed")
        self.env.process(self._switch_on(priority=priority))

    @ignore_causes()
    def _switch_off(
        self, force=False, require_executor=True, priority=0, max_wait=0
    ):
        """Change machine state to "off".

        State changes:
        off        -> off: No
        on         -> off: Yes
        production -> off: Yes (gracefully or force)
        error      -> off: Yes
        """
        yield self.wjitter()
        if self.state == "off":
            self.warning(f'Cant go from state "{self.state}" to "off"')
            self.emit("switched_off")
            return

        priority = -99999 if force else priority
        require_executor = False if force else require_executor
        with self.execute.request(priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug('Execution ongoing, will not try to go "off"')
                    return
                else:
                    self.debug('Locked executor at "switch_off"')
            else:
                self.debug("Skipping executor waiting at switching off")

            # Turn machine off
            if self.state == "on":
                self.emit("switching_off")
                yield self.wnorm(30, 50)
                self.state = "off"
                self.emit("switched_off")
            elif self.state == "production":
                self.emit("switching_off")

                # Try interrupt production
                cause = ManualSwitchOffCause(force=force)
                self.env.process(
                    self._interrupt_production(
                        cause, require_executor=False, priority=priority
                    )
                )
                self.debug("Waiting for production to stop")
                yield self.events["production_stopped"]

                yield self.wjitter()
                self.state = "off"
                self.emit("switched_off")
            elif self.state == "error":
                self.emit("switching_off")

                # Try interrupt production
                cause = ManualSwitchOffCause(force=True)
                yield self.env.process(
                    self._interrupt_production(cause, require_executor=False)
                )

                yield self.wjitter()
                self.state = "off"
                self.emit("switched_off")

        if require_executor:
            self.debug('Released executor at "switch_off"')

    def press_off(self, force=False, priority=-10, max_wait=120):
        yield self.wjitter()
        self.emit("off_button_pressed")
        self.env.process(
            self._switch_off(force=force, priority=priority, max_wait=max_wait)
        )

    def _switch_production(
        self, require_executor=True, priority=0, max_wait=0
    ):
        """Change machine state to "off".

        State changes:
        off        -> production: No, always through "on"
        on         -> production: Yes
        production -> production: No
        error      -> production: No
        """
        yield self.wjitter()
        if not self.state == "on":
            self.warning(f'Cant go from state "{self.state}" to "production"')
            return

        with self.execute.request(priority=priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug(
                        'Execution ongoing, will not try to go "production"'
                    )
                    return
            else:
                self.warning(
                    "Skipping executor waiting at switching production"
                )

            # Start production
            self.emit("switching_production")
            yield self.wjitter()
            self.procs["production"] = self.env.process(self._production())
            self.state = "production"
            self.emit("switched_production")

    @ignore_causes()
    def _switch_program(
        self, program, require_executor=True, priority=0, max_wait=10
    ):
        """Switch program on machine

        State:
        off        : Yes (internally only)
        on         : Yes
        production : No
        error      : Yes (internally only)
        """
        if program not in self.programs:
            self.error(f'Program "{program}" does not exist, returning')
            return

        yield self.wjitter()
        if self.state == "production":
            self.warning(
                "Cant change program during production run, please "
                "stop production first"
            )
            return

        with self.execute.request(priority=priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug(
                        f"Timed out when trying to switch program to "
                        f"{program}"
                    )
                    return
                else:
                    self.debug('Locked executor at "switch_program"')
            else:
                self.debug("Skipping executor waiting at switching program")

            assert self.state != "production", "Something went wrong :("
            self.emit("switching_program")
            yield self.wnorm(60, 120)
            self.program = program
            self.emit("switched_program")

        if require_executor:
            self.debug('Released executor at "switch_program"')

    @ignore_causes()
    def _automated_program_switch(
        self, program, priority=-2, force=False, max_wait=300
    ):
        """Switch production program automatically."""
        if program not in self.programs:
            self.error(f'Program "{program}" does not exist, returning')
            return
        elif self.state == "error":
            self.warning('Automated program not possible in "error" state')
            return
        elif self.state == "off":
            self.warning('Automated program not possible in "off" state')
            return

        yield self.wjitter()

        with self.ui.request(priority=priority) as ui:
            results = yield ui | self.env.timeout(max_wait)
            if ui not in results:
                self.debug("UI is not responsive, will not change program")
                return

            with self.execute.request(priority=priority) as executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug(
                        "Execution ongoing, will not change program and "
                        "start production"
                    )
                    return

                self.emit("switching_program_automatically")

                if self.state != "on":
                    cause = ProgramSwitchCause(force=force)
                    self.env.process(
                        self._switch_on(require_executor=False, cause=cause)
                    )
                    yield self.events["switched_on"]

                self.env.process(
                    self._switch_program(program, require_executor=False)
                )
                yield self.events["switched_program"]

                self.env.process(
                    self._switch_production(require_executor=False)
                )
                yield self.events["production_started"]

                self.emit("switched_program_automatically")

    @ignore_causes()
    def switch_program(self, program, priority=-1, max_wait=60):
        yield self.wjitter()
        with self.ui.request() as ui:
            results = yield ui | self.env.timeout(0)
            if ui not in results:
                self.debug(
                    'UI is not responsive, will not try to "switch_program"'
                )
                return

            self.env.process(
                self._switch_program(
                    program, priority=priority, max_wait=max_wait
                )
            )
            yield self.events["switched_program"]

    def start_production(self, program=None, max_wait=60):
        with self.ui.request() as ui:
            yield self.wjitter()
            results = yield ui | self.env.timeout(max_wait)
            if ui not in results:
                self.debug(
                    'UI is not responsive, will not try to go "production"'
                )
                return

            if program is not None:
                yield self.env.process(
                    self._switch_program(program, max_wait=max_wait)
                )

            self.env.process(self._switch_production())

    def stop_production(self, force=False, max_wait=60):
        with self.ui.request() as ui:
            yield self.wjitter()
            results = yield ui | self.env.timeout(max_wait)
            if ui not in results:
                self.debug(
                    "UI is not responsive, cannot try to stop production"
                )
                return

            cause = ManualStopProductionCause(force=force)
            self.env.process(self._interrupt_production(cause))

    def _interrupt_production(
        self, cause=None, require_executor=True, priority=0, max_wait=0
    ):
        if self.production_interruption_ongoing:
            self.warning("Production interruption already ongoing, returning")
            return

        yield self.wjitter()
        with self.execute.request(priority=priority) as executor:
            if require_executor:
                results = yield executor | self.env.timeout(max_wait)
                if executor not in results:
                    self.debug("Execution ongoing, wont interrupt production")
                    return
            else:
                self.warning(
                    "Skipping executor waiting at interrupt production"
                )

            if not self.production_interruption_ongoing:
                production_proc = self.procs.get("production")
                if production_proc and production_proc.is_alive:
                    code = (
                        cause.code if cause is not None else UnknownCause.code
                    )
                    self.production_interrupt_code = code
                    production_proc.interrupt(cause)
            else:
                self.warning(
                    "Cannot interrupt production, its ongoing already"
                )

    def _production(self):
        """Machine producing products.

        State changes:
        production -> production: No, always through "on"
        on         -> production: Yes
        production -> production: No
        error      -> production: No

        TODO: The whole issue/cause should be refactored, e.g. production issue
              should cause production interruption cause to be
              AutomaticStopProduction etc.
        """
        yield self.wjitter()
        # TODO: Cleanup the triggers + prio handling with try etc.
        if self.program is None:
            self.warning("Production cannot be started with no program set")
            return

        self.emit("production_started")
        self.production_interrupt_code = 0
        self.error_code = 0
        while True:
            try:
                # Run one batch of program
                self.procs["program_run"] = self.env.process(
                    self.program.run(self)
                )
                yield self.procs["program_run"]
            except simpy.Interrupt as i:
                self.info(f"Production interrupted: {i}")
                self.emit("production_interrupted")
                self.production_interruption_ongoing = True
                cause_or_issue = i.cause
                self.production_interrupt_code = cause_or_issue.code

                # Causes are reasons to interrupt batch process
                if isinstance(cause_or_issue, BaseCause):
                    self.procs["program_run"].interrupt(cause_or_issue)
                    yield self.procs["program_run"]

                # Issues need to be resolved by operators but cause batch
                # interruption, if the batch is still running
                elif isinstance(cause_or_issue, ProductionIssue):
                    yield self.env.process(self._switch_error(cause_or_issue))
                    # FIXME: Are we sure that production can't be in progress?
                    self.emit("production_stopped_from_error")
                else:
                    raise i
                self.emit("production_stopped")
                break

        self.production_interruption_ongoing = False

    @ignore_causes()
    def _switch_error(self, issue):
        """Machine is in erroneous state.

        State changes:
        off        -> error: No
        on         -> error: Yes
        production -> error: Yes
        error      -> error: No
        """
        yield self.wjitter()
        if self.state not in ["on", "production"]:
            self.warning(f'Cant go from state "{self.state}" to "error"')
            if self.state == "error":
                self.warning("More than one error is not implemented!")
            return

        self.emit("issue_occurred", issue)
        self.emit("switching_error")
        with self.ui.request(priority=-9999) as ui:
            yield ui  # Should get immediately based on priority

            with self.execute.request(priority=-9999) as executor:
                yield executor

                self.debug('Locked executor at "switch_error"')

                yield self.wjitter()
                self.state = "error"
                self.error_code = issue.code
                self.emit("switched_error")

                # Try stop production
                cause = AutomatedStopProductionCause(issue, force=True)
                yield self.env.process(
                    self._interrupt_production(
                        cause=cause, require_executor=False
                    )
                )
                self.emit("production_stopped_from_error")

                # Give execution back once clear issue from operator
                yield self.events["clearing_issue"]

            self.debug('Released executor at "switch_error"')

            # UI locked until issue cleared entirely
            yield self.events["issue_cleared"]

        self.debug("UI released")

    def reboot(self, priority=-1):
        yield self.wjitter()
        if self.state == "off":
            self.warning('Tried to reboot machine that is "off"')
            return

        self.env.process(
            self._switch_off(require_executor=False, priority=priority)
        )
        yield self.events["switched_off"]
        self.env.process(
            self._switch_on(require_executor=False, priority=priority)
        )
        yield self.events["switched_on"]
        self.debug("Rebooted")

    def clear_issue(self):
        """Clear an existing issue."""
        if self.state == "error":
            self.emit("clearing_issue")
            yield self.wnorm(20)
            yield self.env.process(self.reboot())
            self.error_code = 0
            self.emit("issue_cleared")
        else:
            self.warning("No issues to be cleared")
            return
