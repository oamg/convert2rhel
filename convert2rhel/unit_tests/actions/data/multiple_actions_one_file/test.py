__metaclass__ = type

from convert2rhel import actions


class RealTest(actions.Action):
    id = "REALTEST"

    def run(self):
        pass


class SecondTest(actions.Action):
    id = "SECONDTEST"

    def run(self):
        pass
