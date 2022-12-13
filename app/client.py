"""OPC-UA Client."""


import asyncio
import logging
import os
import sys

from asyncua import Client


URL = os.environ['SERVER_URL']

NAMESPACE = os.environ['SERVER_NAMESPACE']


async def main():
    logger = logging.getLogger(__name__)
    logger.info(f'Connecting to {URL} ...')

    async with Client(url=URL) as client:
        # Find the namespace index
        nsidx = await client.get_namespace_index(NAMESPACE)
        logger.info(f'Namespace Index for "{NAMESPACE}": {nsidx}')

        obj = await client.nodes.root.get_child(
            ['0:Objects', f'{nsidx}:Factory']
        )
        while True:
            await asyncio.sleep(1)
            for var in await obj.get_variables():
                value = await var.read_value()
                name = await var.read_description()
                logger.info(f'Value of {name.Text!r}: {value!r}')


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)-7s - %(message)s',
        datefmt='%H:%M:%S'
    )
    asyncio.run(main())
