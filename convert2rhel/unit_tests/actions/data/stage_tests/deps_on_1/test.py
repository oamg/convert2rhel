from convert2rhel import actions


class TestI(actions.Action):
    id = "TESTI"
    dependencies = ("REALTEST",)

    def run(self):
        super().run()


class TestII(actions.Action):
    id = "TESTII"
    dependencies = ("REALTEST", "FOURTHTEST")

    def run(self):
        super().run()
