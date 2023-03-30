from convert2rhel import actions


class ATest(actions.Action):
    id = "ATEST"
    dependencies = ("BTEST",)

    def run(self):
        super(ATest, self).run()
        pass


class BTest(actions.Action):
    id = "BTEST"

    def run(self):
        super(BTest, self).run()
        self.set_status(status=actions.STATUS_CODES["ERROR"], error_id="BTEST_FAILURE", message="failure message")
