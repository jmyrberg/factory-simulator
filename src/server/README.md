# Factory Simulator - OPC UA Server and Client

Simulate factory as an OPC UA server by running the simulation in it's own thread and querying the factory state at given intervals.

## Instructions

Build

```shell
docker build . -t factory-simulator -f src/server/Dockerfile
```

Run server (copy `.env` from [.example.env](../../.example.env))

```shell
docker run -p 4840:4840 --env-file .env -v $(pwd):/opt/app factory-simulator
```

Run client

```shell
export $( grep -vE "^(#.*|\s*)$" .env ) && \
python -m src.server.client
```

## Architecture

```mermaid
graph LR;
    sim(Factory simulation) -- Get state --> collector(Data collector)
    collector -- Get values --> server(OPC-UA server)
    server -- Set values --> variables(Variables)
    variables -- Get values --> server
    server -- Serve values --> client(Client)
```

The data collector variables are defined in [factory.yml](../../config/factory.yml).
