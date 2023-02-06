__metaclass__ = type

from convert2rhel.actions import Action as Foo


class RealTest(Foo):
    id = "REALTEST"

    def run(self):
        pass
