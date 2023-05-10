from convert2rhel import actions


class ATest(actions.Action):
    id = "ATEST"
    dependencies = ("BTEST",)

    def run(self):
        super(ATest, self).run()
        return


class BTest(actions.Action):
    id = "BTEST"

    def run(self):
        super(BTest, self).run()
        self.set_status(
            level=actions.STATUS_CODES["ERROR"],
            id="BTEST_FAILURE",
            title="failure title",
            description="failure description",
            diagnosis="failure diagnosis",
            remediation="failure remediation",
        )
