__metaclass__ = type

from convert2rhel import actions


class TestAction1(actions.Action):
    id = "TestAction1"

    def run(self):
        pass
