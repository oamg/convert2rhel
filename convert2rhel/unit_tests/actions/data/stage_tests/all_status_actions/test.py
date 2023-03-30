from convert2rhel import actions


class FatalTest(actions.Action):
    id = "FATALTEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super(FatalTest, self).run()
        self.set_result(status="FATAL", message="Fatally failed")


class ErrorTest(actions.Action):
    id = "ERRORTEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super(ErrorTest, self).run()
        self.set_result(status="ERROR", message="Failed on an error")


class OverridableTest(actions.Action):
    id = "OVERRIDABLETEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super(OverridableTest, self).run()
        self.set_result(status="OVERRIDABLE", message="Check failed but user may override")


# Skip because one dependency has failed
class SkipSingleTest(actions.Action):
    id = "SKIPSINGLETEST"
    dependencies = ("ERRORTEST",)

    def run(self):
        super(SkipSingleTest, self).run()
        pass


# Skip because of multiple dependencies have failed
class SkipMultipleTest(actions.Action):
    id = "SKIPMULTIPLETEST"
    dependencies = ("ERRORTEST", "OVERRIDABLETEST")

    def run(self):
        super(SkipMultipleTest, self).run()
        pass


class WarningTest(actions.Action):
    id = "WARNINGTEST"

    def run(self):
        super(WarningTest, self).run()
        self.set_result(status="WARNING", message="User disabled check")


class SuccessTest(actions.Action):
    id = "SUCCESSTEST"

    def run(self):
        super(SuccessTest, self).run()
        pass
