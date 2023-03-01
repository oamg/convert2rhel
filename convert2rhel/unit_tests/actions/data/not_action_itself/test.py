from convert2rhel import actions


AlternateName = actions.Action


class RealTest(AlternateName):
    id = "REALTEST"

    def run(self):
        pass


class OtherTest(actions.Action):
    id = "OTHERTEST"

    def run(self):
        pass
