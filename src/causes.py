"""Interruptions."""


class BaseCause(BaseException):

    def __init__(self, name=None):
        self.name = name or ''

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r})'


class ManualSwitchOffCause(BaseCause):
    """Machine is switched off."""
    def __init__(self, force=False, **kwargs):
        super().__init__(kwargs.get('name'))
        self.force = force


class ProgramSwitchCause(BaseCause):
    """Program is changed to something else."""
    def __init__(self, force=False, **kwargs):
        super().__init__(kwargs.get('name'))
        self.force = force


class UnknownCause(BaseCause):
    """Unknown cause."""
