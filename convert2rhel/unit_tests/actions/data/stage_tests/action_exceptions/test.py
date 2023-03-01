import logging

from convert2rhel import actions


loginst = logging.getLogger(__name__)


class DivideByZeroTest(actions.Action):
    id = "DIVIDEBYZEROTEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super(DivideByZeroTest, self).run()
        return 1 / 0


class LogCriticalTest(actions.Action):
    id = "LOGCRITICALTEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super(LogCriticalTest, self).run()
        loginst.critical("Critical log will cause a SystemExit.")


class SuccessTest(actions.Action):
    id = "SUCCESSTEST"

    def run(self):
        super(SuccessTest, self).run()
        return
