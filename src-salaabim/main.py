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
import sys
print(sys.path)

import uuid

from datetime import datetime, timedelta
from pytz import timezone

import salabim as sim

from matplotlib import pyplot as plt

from src.machine import Machine
from src.operator import Operator
from src.containers import Tank


env = sim.Environment(
    time_unit='minutes',
    datetime0=datetime.now(timezone('Europe/Helsinki')),
    trace=True
)

env.produced_parts = 0
# tank = Tank()
machine = Machine()
operator = Operator().assign_machine(machine)

# Monitoring

# Run
env.animate(False)
env.run(60 * 24 * 7)
