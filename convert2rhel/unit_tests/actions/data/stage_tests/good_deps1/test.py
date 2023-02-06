__metaclass__ = type

from convert2rhel import actions


class RealTest(actions.Action):
    id = "REALTEST"

    def run(self):
        super(RealTest, self).run()
        return


class SecondTest(actions.Action):
    id = "SECONDTEST"
    dependencies = ("REALTEST",)

    def run(self):
        super(SecondTest, self).run()
        return


class ThirdTest(actions.Action):
    id = "THIRDTEST"
    dependencies = ("REALTEST",)

    def run(self):
        super(ThirdTest, self).run()
        return


class FourthTest(actions.Action):
    id = "FOURTHTEST"
    dependencies = ("SECONDTEST", "THIRDTEST")

    def run(self):
        super(FourthTest, self).run()
        return
