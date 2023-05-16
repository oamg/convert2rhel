from convert2rhel import actions


class RealTest(actions.Action):
    id = "REALTEST"

    def run(self):
        pass


class NotAction(object):
    pass


class AlsoNotAction(NotAction):
    pass
