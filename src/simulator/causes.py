"""Interruptions."""


class BaseCause(BaseException):
    code = 0

    def __init__(self, name=None):
        self.name = name or "BaseCause"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name!r})"


class ManualSwitchOffCause(BaseCause):
    """Machine is switched off."""

    code = 1

    def __init__(self, force=False, **kwargs):
        super().__init__(kwargs.get("name"))
        self.force = force
        self.code += 900 * int(self.force)


class ManualStopProductionCause(BaseCause):
    """Production is stopped manually."""

    code = 2

    def __init__(self, force=False, **kwargs):
        super().__init__(kwargs.get("name"))
        self.force = force
        self.code += 900 * int(self.force)


class AutomatedStopProductionCause(BaseCause):
    """Production is stopped manually."""

    code = 3

    def __init__(self, force=False, **kwargs):
        super().__init__(kwargs.get("name"))
        self.force = force
        self.code += 900 * int(self.force)


class ProgramSwitchCause(BaseCause):
    """Program is changed to something else."""

    code = 4

    def __init__(self, force=False, **kwargs):
        super().__init__(kwargs.get("name"))
        self.force = force
        self.code += 900 * int(self.force)


class WorkStoppedCause(BaseCause):
    """Operator has left work."""

    code = 5


class UnknownCause(BaseCause):
    """Unknown cause."""

    code = 999
