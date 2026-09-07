from convert2rhel import actions


class ATest(actions.Action):
    id = "ATEST"
    dependencies = ("BTEST",)

    def run(self):
        super().run()


class BTest(actions.Action):
    id = "BTEST"

    def run(self):
        super().run()
        self.set_status(
            level=actions.STATUS_CODES["ERROR"],
            id="BTEST_FAILURE",
            title="failure title",
            description="failure description",
            diagnosis="failure diagnosis",
            remediations="failure remediations",
        )
