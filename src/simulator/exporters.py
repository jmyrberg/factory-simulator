"""Exporters."""


import csv

import simpy

from src.simulator.base import Base
from src.simulator.utils import wait_factory


def get_exporter_by_type(exporter: str):
    """Get exporter based on given type."""
    exporter = exporter.strip().lower()
    if exporter == "csv":
        return CSVExporter
    else:
        raise ValueError(f"Unknown exporter '{exporter}'")


class Exporter(Base):
    def __init__(self, env, name=None, uid=None):
        super().__init__(env, name=name, uid=uid)


class CSVExporter(Exporter):
    def __init__(
        self,
        env: simpy.Environment | simpy.RealtimeEnvironment,
        filepath: str,
        collector: dict | None = None,
        interval_secs: int = 60,
        name: str = "csv-exporter",
        uid: str | None = None,
    ):
        """Export simulation data as CSV file.

        Args:
            filepath: Filepath to save CSV into.
            collector (optional): Parsed collector dictionary.
                If None, all data will be collected. Defaults to None.
            interval_secs (optional): Data snapshot interval in seconds.
                Defaults to 60.
            name (optional): Name of the CSV exporter. Defaults to
                "csv-exporter".
            uid (optional): Unique ID of the object. Defaults to None.
        """
        super().__init__(env, name=name, uid=uid)
        self.filepath = filepath
        self.collector = collector
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
            state = self.env.factory.get_state(collector=self.collector)

            if self.fieldnames is None and self.writer is None:
                self.fieldnames = list(state.keys())
                self.info(f"Fieldnames: {self.fieldnames!r}")

                self.writer = csv.DictWriter(
                    self.file, fieldnames=self.fieldnames
                )
                self.writer.writeheader()

            # Data
            self.writer.writerow(state)
            yield self.env.timeout(self.interval_secs)

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()
