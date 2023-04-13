import logging
import sys

from src.simulator.factory import Factory

logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)-7s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


logger.info("Starting simulation")
factory = Factory.from_config("config/factory.yml")
factory.run(7)
