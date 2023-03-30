from convert2rhel import actions


class RealTest(actions.Action):
    id = "REALTEST"

    def run(self):
        super(RealTest, self).run()
        pass


class SecondTest(actions.Action):
    id = "SECONDTEST"
    dependencies = ("REALTEST",)

    def run(self):
        super(SecondTest, self).run()
        pass


class ThirdTest(actions.Action):
    id = "THIRDTEST"
    dependencies = ("REALTEST",)

    def run(self):
        super(ThirdTest, self).run()
        pass


class FourthTest(actions.Action):
    id = "FOURTHTEST"
    dependencies = ("SECONDTEST", "THIRDTEST")

    def run(self):
        super(FourthTest, self).run()
        pass
