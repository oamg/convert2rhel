from convert2rhel import actions


class RealTest(actions.Action):
    id = "REALTEST"

    def run(self):
        super().run()


class SecondTest(actions.Action):
    id = "SECONDTEST"
    dependencies = ("REALTEST",)

    def run(self):
        super().run()


class ThirdTest(actions.Action):
    id = "THIRDTEST"
    dependencies = ("REALTEST",)

    def run(self):
        super().run()


class FourthTest(actions.Action):
    id = "FOURTHTEST"
    dependencies = ("SECONDTEST", "THIRDTEST")

    def run(self):
        super().run()
