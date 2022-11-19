"""Interruptions."""


class BaseIssue:
    def __init__(self, name=None):
        self.name = name or ''

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r})'


class ProductionIssue(BaseIssue):
    """Issue arisen from production process."""


class LowConsumableLevelIssue(ProductionIssue):
    def __init__(self, consumable, **kwargs):
        super().__init__(kwargs.get('name'))
        self.consumable = consumable


class UnknownIssue(BaseIssue):
    """Unknown issue."""