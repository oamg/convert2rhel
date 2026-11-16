from convert2rhel import actions


class BadTest1(actions.Action):
    id = "BADTEST1"
    dependencies = ("BADTEST2",)

    def run(self):
        super().run()


class BadTest2(actions.Action):
    id = "BADTEST2"
    dependencies = ("BADTEST1",)

    def run(self):
        super().run()
