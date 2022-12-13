"""OPC-UA server."""


import asyncio
import concurrent
import logging
import os
import sys
print(sys.path)

from copy import deepcopy

from asyncua import Server

from src.factory import Factory


URL = os.environ['SERVER_URL']

NAMESPACE = os.environ['SERVER_NAMESPACE']


async def setup_server(vars_dict, logger):
    # Setup server
    server = Server()
    await server.init()
    server.set_endpoint(URL)

    idx = await server.register_namespace(NAMESPACE)

    # Variables
    myobj = await server.nodes.objects.add_object(idx, 'Factory')
    vars = deepcopy(vars_dict)
    for var_name, d in vars_dict.items():
        var = await myobj.add_variable(idx, var_name, d['val'])
        vars[var_name] = {**d, 'var': var}

    return server, vars


async def run_server(server, vars_dict, logger):
    logger.info('Starting server')
    async with server:
        while True:
            await asyncio.sleep(1)
            for var_name, d in vars_dict.items():
                value = await d['var'].get_value()
                logger.debug(f'Variable {var_name} value: {value!r}')


async def main():
    logger = logging.getLogger(__name__)

    # Run factory in it's own thread
    factory = Factory.from_config('config/factory.yml', real=True)
    vars_dict = factory.get_vars_dict()

    loop = asyncio.get_running_loop()
    executor = concurrent.futures.ThreadPoolExecutor()
    loop.run_in_executor(executor, factory.run)
    executor.shutdown(wait=False)

    # Setup and run server
    server, vars = await setup_server(vars_dict, logger)
    run_server_task = asyncio.create_task(run_server(server, vars, logger))

    # Update variables
    update_task = asyncio.create_task(factory.update_vars(vars))

    await asyncio.gather(run_server_task, update_task)


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)-7s - %(message)s',
        datefmt='%H:%M:%S'
    )
    asyncio.run(main(), debug=True)
