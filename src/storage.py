"""Storage containers."""


import salabim as sim


class Container(sim.Component):

    def setup(self, init_level=1_000):
        self.level = sim.Resource('level', init_level, anonymous=True)

    def get(self, qty):
        yield self.get((self.level, qty))

    def put(self, qty):
        yield self.put((self.level, qty))

    @property
    def level(self):
        return self.level.available_quantity()
