"""Run simulation."""


import logging
import sys

import arrow
import simpy

from src.machine import Machine
from src.operator import Operator


logging.basicConfig(
     stream=sys.stdout,
     level=logging.INFO,
     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
     datefmt='%H:%M:%S'
 )
logger = logging.getLogger(__name__)
logger.info('Starting simulation')

start = arrow.now()
env = simpy.Environment(initial_time=start.timestamp())
machine = Machine(env)
operator = Operator(env).assign_machine(machine)

env.run(until=start.timestamp() + 2 * 24 * 60 * 60)
