"""OPC-UA Client."""


import asyncio
import json
import logging
import os
import sys

from asyncua import Client


SERVER_ENDPOINT = os.environ['SERVER_ENDPOINT']
SERVER_NAMESPACE = os.environ['SERVER_NAMESPACE']
SERVER_PASSWORD = os.environ['SERVER_PASSWORD']
SERVER_USERNAME = os.environ['SERVER_USERNAME']
POLL_INTERVAL_SECS = 5


async def main():
    logger = logging.getLogger(__name__)
    logger.info(f'Connecting to {SERVER_ENDPOINT} ...')

    client = Client(url=SERVER_ENDPOINT)
    client.set_user(SERVER_USERNAME)
    client.set_password(SERVER_PASSWORD)

    await client.connect()

    try:
        # Find the namespace index
        nsidx = await client.get_namespace_index(SERVER_NAMESPACE)
        logger.info(f'Namespace Index for "{SERVER_NAMESPACE}": {nsidx}')

        obj = await client.nodes.root.get_child(
            ['0:Objects', f'{nsidx}:Factory']
        )
        while True:
            await asyncio.sleep(POLL_INTERVAL_SECS)
            all_vals = {}
            for var in await obj.get_variables():
                value = await var.read_value()
                name = await var.read_description()
                all_vals[name.Text] = value

            logger.info(f'Values:\n{json.dumps(all_vals, indent=4)}')
    finally:
        await client.disconnect()


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    asyncio.run(main())
