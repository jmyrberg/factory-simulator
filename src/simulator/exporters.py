"""Exporters."""


import csv
import json

from src.simulator.base import Base
from src.simulator.utils import wait_factory


def get_exporter_by_type(exporter):
    exporter = exporter.strip().lower()
    if exporter == "csv":
        return CSVExporter
    elif exporter == "jsonline":
        return JSONLineExporter
    else:
        raise ValueError(f"Unknown exporter '{exporter}'")


class Exporter(Base):
    def __init__(self, env, name=None, uid=None):
        super().__init__(env, name=name, uid=uid)


class CSVExporter(Exporter):
    def __init__(
        self,
        env,
        filepath: str,
        names=None,
        interval_secs=60,
        name="csv-exporter",
        uid=None,
    ):
        super().__init__(env, name=name, uid=uid)
        self.filepath = filepath
        self.names = names
        self.interval_secs = interval_secs

        # Internal
        self.file = open(filepath, "w")
        self.writer = None
        self.fieldnames = None

        self.procs = {"write": self.env.process(self._write())}

    @wait_factory
    def _write(self):
        # TODO: Get next full minute
        yield self.env.timeout(10 * self.interval_secs)
        while True:
            state = self.env.factory.state

            if self.writer is None:
                if self.names is None:
                    self.fieldnames = list(state.keys())
                else:
                    self.fieldnames = self.names

                self.info(f"Fieldnames: {self.fieldnames!r}")
                self.writer = csv.DictWriter(
                    self.file, fieldnames=self.fieldnames
                )
                self.writer.writeheader()

            # Data
            row = {k: state.get(k) for k in self.fieldnames}
            self.writer.writerow(row)
            yield self.env.timeout(self.interval_secs)

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()


class JSONLineExporter(Exporter):
    def __init__(
        self,
        env,
        filepath: str,
        interval_secs=60,
        name="jsonline-exporter",
        uid=None,
    ):
        super().__init__(env, name=name, uid=uid)
        self.filepath = filepath
        self.interval_secs = interval_secs

        # Internal
        self.file = open(filepath, "w")
        self.file.write("[")

        self.procs = {"write": self.env.process(self._write())}

    @wait_factory
    def _write(self):
        # TODO: Get next full minute
        yield self.env.timeout(10 * self.interval_secs)
        while True:
            state = self.env.factory.state
            jsonline = json.dumps(state, default=str)
            self.file.write(f"\n{jsonline}")

            yield self.env.timeout(self.interval_secs)

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.write("\n]")
        self.file.close()
