"""OPC-UA server."""


import asyncio
import concurrent
import logging
import os
import sys

from asyncua import Server
from asyncua.server.users import User, UserRole

from src.app.interface import get_vars_dict, update_vars
from src.simulator.factory import Factory


FACTORY_CONFIG_PATH = os.getenv('FACTORY_CONFIG_PATH', 'config/factory.yml')
SERVER_ENDPOINT = os.environ['SERVER_ENDPOINT']
SERVER_LOGLEVEL = os.getenv('SERVER_LOGLEVEL', 'WARNING').upper()
SERVER_NAMESPACE = os.environ['SERVER_NAMESPACE']
SERVER_PASSWORD = os.environ['SERVER_PASSWORD']
SERVER_USERNAME = os.environ['SERVER_USERNAME']
SIMULATOR_LOGLEVEL = os.getenv('SIMULATOR_LOGLEVEL', 'INFO').upper()


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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    logger = logging.getLogger('src.app.server')
    logger.info(f'{FACTORY_CONFIG_PATH=}')
    logger.info(f'{SERVER_ENDPOINT=}')
    logger.info(f'{SERVER_LOGLEVEL=}')
    logger.info(f'{SERVER_NAMESPACE=}')
    logger.info(f'{SIMULATOR_LOGLEVEL=}')

    server_loggers = ['asyncua', '__main__', 'src.app']
    for server_logger in server_loggers:
        logging.getLogger(server_logger).setLevel(SERVER_LOGLEVEL)

    return logger


async def setup_server(vars_dict):
    server = Server(user_manager=BasicAuthUserManager())
    await server.init()
    server.set_endpoint(SERVER_ENDPOINT)
    # https://github.com/FreeOpcUa/opcua-asyncio/pull/687
    server.set_match_discovery_client_ip(False)
    server.set_security_IDs(['Username'])

    # Variables
    idx = await server.register_namespace(SERVER_NAMESPACE)
    factory_obj = await server.nodes.objects.add_object(idx, 'Factory')
    for var_name in vars_dict.keys():
        default_val = vars_dict[var_name]['val']
        var = await factory_obj.add_variable(idx, var_name, default_val)
        vars_dict[var_name]['var'] = var

    return server, vars_dict


async def run_server(server, vars_dict):
    logger.info('Starting server')
    async with server:
        while True:
            await asyncio.sleep(1)
            # for var_name, d in vars_dict.items():
            #     value = await d['var'].get_value()
            #     logger.debug(f'Variable {var_name} value: {value!r}')


async def main():
    # Run factory in it's own thread
    factory = Factory.from_config(FACTORY_CONFIG_PATH, real=True)
    vars_dict = get_vars_dict(factory)

    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()
    loop.run_in_executor(executor, factory.run)
    executor.shutdown(wait=False)

    # Setup and run server
    server, vars_dict = await setup_server(vars_dict)
    run_server_task = asyncio.create_task(
        run_server(server, vars_dict))

    # Update variables
    update_task = asyncio.create_task(update_vars(vars_dict))

    await asyncio.gather(run_server_task, update_task)


if __name__ == '__main__':
    logger = setup_logging()
    asyncio.run(main())
