"""Factory machine simulator.

Components:
- Machine status
- Consumable
- Consumable tank

- Environment: Temperature


Material flow:
   ( TANK )
-> ( RAW MATERIAL )
-> ( MACHINE )
-> ( PRODUCT )

Processes interrupting material flow and states:
- Generate raw material in tank
- Consume raw material from tank
- Machine converts raw material into end product with given capacity
- End product is created
"""


import uuid

from datetime import datetime, timedelta
from pytz import timezone

import salabim as sim

from matplotlib import pyplot as plt

from src.machine import Machine
from src.operator import Operator
from src.storage import Container


env = sim.Environment(
    time_unit='minutes',
    datetime0=datetime.now(timezone('Europe/Helsinki')),
    trace=True
)

env.produced_parts = 0
storage = Container()
machine = Machine()
operator = Operator()

# Monitoring
sim.AnimateMonitor(
    machine.state.all_monitors()[-1],
    vertical_map=lambda x: 'off idle on error'.split().index[x],
    x=10, y=200,
    horizontal_scale=10, vertical_scale=10
)

# Run
env.animate(False)
env.run(60 * 24 * 2)
