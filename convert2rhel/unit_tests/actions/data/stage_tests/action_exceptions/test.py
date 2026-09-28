from convert2rhel import actions
from convert2rhel.logger import root_logger

logger = root_logger.getChild(__name__)


class DivideByZeroTest(actions.Action):
    id = "DIVIDEBYZEROTEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super().run()
        return 1 / 0


class LogCriticalTest(actions.Action):
    id = "LOGCRITICALTEST"
    dependencies = ("SUCCESSTEST",)

    def run(self):
        super().run()
        logger.critical("Critical log will cause a SystemExit.")


class SuccessTest(actions.Action):
    id = "SUCCESSTEST"

    def run(self):
        super().run()
