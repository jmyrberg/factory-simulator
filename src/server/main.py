"""OPC-UA server."""


import asyncio
import concurrent
import logging
import os
import sys

from functools import partial

from asyncua import Server
from asyncua import ua
from asyncua.server.users import User, UserRole

from src.simulator.factory import Factory

FACTORY_CONFIG_PATH = os.getenv("FACTORY_CONFIG_PATH", "config/factory.yml")
FACTORY_COLLECTOR_NAME = os.getenv("FACTORY_COLLECTOR_NAME", "default")
SERVER_ENDPOINT = os.environ["SERVER_ENDPOINT"]
SERVER_LOGLEVEL = os.getenv("SERVER_LOGLEVEL", "WARNING").upper()
SERVER_NAMESPACE = os.environ["SERVER_NAMESPACE"]
SERVER_PASSWORD = os.environ["SERVER_PASSWORD"]
SERVER_USERNAME = os.environ["SERVER_USERNAME"]
SERVER_WRITE_INTERVAL_SECS = int(os.getenv("SERVER_WRITE_INTERVAL_SECS", 5))
SIMULATOR_LOGLEVEL = os.getenv("SIMULATOR_LOGLEVEL", "INFO").upper()


class BasicAuthUserManager:
    def get_user(self, isession, username, password, certificate=None):
        if username == SERVER_USERNAME and password == SERVER_PASSWORD:
            return User(role=UserRole.User)
        else:
            return None


def setup_logging():
    logging.basicConfig(
        stream=sys.stdout,
        level=SIMULATOR_LOGLEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("src.server.main")
    logger.info(f"{FACTORY_CONFIG_PATH=}")
    logger.info(f"{FACTORY_COLLECTOR_NAME=}")
    logger.info(f"{SERVER_ENDPOINT=}")
    logger.info(f"{SERVER_LOGLEVEL=}")
    logger.info(f"{SERVER_NAMESPACE=}")
    logger.info(f"{SERVER_WRITE_INTERVAL_SECS=}")
    logger.info(f"{SIMULATOR_LOGLEVEL=}")

    server_loggers = ["asyncua", "__main__", "src.server"]
    for server_logger in server_loggers:
        logging.getLogger(server_logger).setLevel(SERVER_LOGLEVEL)

    return logger


async def setup_server(collector):
    server = Server(user_manager=BasicAuthUserManager())
    await server.init()
    server.set_endpoint(SERVER_ENDPOINT)
    # https://github.com/FreeOpcUa/opcua-asyncio/pull/687
    server.set_match_discovery_client_ip(False)
    server.set_security_IDs(["Username"])

    # Variables
    logger.info('Setting up variables...')
    idx = await server.register_namespace(SERVER_NAMESPACE)
    factory_obj = await server.nodes.objects.add_object(idx, "Factory")
    dvars = {}
    for d in collector["variables"].values():
        logger.info(d)
        if "dtype" in d:
            varianttype = getattr(ua.VariantType, d["dtype"])
        else:
            varianttype = None

        dvars[d["name"]] = await factory_obj.add_variable(
            idx,
            d["name"],
            d.get("default"),
            varianttype=varianttype
        )

    return server, dvars


async def run_server(server):
    logger.info("Starting server")
    async with server:
        while True:
            await asyncio.sleep(1)
            # for name, var in dvars.items():
            #     value = await var.get_value()
            #     logger.debug(f'Variable {name} value: {value!r}')


async def update_vars(state_func, dvars):
    logger.info("Variable update loop started")
    while True:
        await asyncio.sleep(SERVER_WRITE_INTERVAL_SECS)
        state = state_func()
        for name, value in state.items():
            await dvars[name].write_value(value)


async def main():
    # Run factory in it's own thread
    factory = Factory.from_config(FACTORY_CONFIG_PATH, real=True)
    collector = factory.collectors[FACTORY_COLLECTOR_NAME]

    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()
    loop.run_in_executor(executor, factory.run)
    executor.shutdown(wait=False)

    # Setup and run server
    server, dvars = await setup_server(collector)
    run_server_task = asyncio.create_task(run_server(server))

    # Update variables
    state_func = partial(factory.get_state, collector)
    update_task = asyncio.create_task(update_vars(state_func, dvars))

    await asyncio.gather(run_server_task, update_task)


if __name__ == "__main__":
    logger = setup_logging()
    asyncio.run(main())
