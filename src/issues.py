"""Interruptions."""


class BaseIssue(BaseException):
    def __init__(self, name=None):
        self.name = name or ''

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r})'


class ProductionIssue(BaseIssue):
    """Issue arisen from production process."""
    priority = 3
    needs_maintenance = False


class ContainerMissingIssue(ProductionIssue):
    def __init__(self, material_or_consumable, **kwargs):
        super().__init__(**kwargs)
        self.material_or_consumable = material_or_consumable


class LowContainerLevelIssue(ProductionIssue):
    def __init__(self, containers, **kwargs):
        super().__init__(**kwargs)
        self.containers = containers


class OverheatIssue(BaseIssue):
    """Machine is overheating."""
    priority = 5
    needs_maintenance = False

    def __init__(self, realized, limit, **kwargs):
        super().__init__(**kwargs)
        self.realized = realized
        self.limit = limit


class OtherCustomerIssue(BaseIssue):
    """Issue from another customer to the maintenance team."""
    priority = 5
    needs_maintenance = True


class ScheduledMaintenanceIssue(BaseIssue):
    """Issue from another customer to the maintenance team."""
    priority = 1
    needs_maintenance = True

    def __init__(self, machine, duration, **kwargs):
        super().__init__(**kwargs)
        self.machine = machine
        self.duration = duration


class UnknownIssue(BaseIssue):
    """Unknown issue."""
