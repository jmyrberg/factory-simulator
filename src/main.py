"""Run simulation."""


import logging
import sys

sys.path.append('./')

import arrow
import matplotlib.pyplot as plt
import pandas as pd
import simpy

from src.machine import Machine
from src.operator import Operator


logging.basicConfig(
     stream=sys.stdout,
     level=logging.DEBUG,
     format='%(asctime)s - %(name)s - %(levelname)-7s - %(message)s',
     datefmt='%H:%M:%S'
 )
logger = logging.getLogger(__name__)
logger.info('Starting simulation')

start = arrow.now('Europe/Helsinki')
env = simpy.Environment(initial_time=start.timestamp())
machine = Machine(env)
operator = Operator(env).assign_machine(machine)

df = pd.DataFrame(operator.data, columns=['ds', 'name', 'value'])
df.plot()
plt.show(block=True)

env.run(until=start.timestamp() + 3 * 24 * 60 * 60)
