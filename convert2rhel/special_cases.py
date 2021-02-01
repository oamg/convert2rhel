import logging

from convert2rhel.systeminfo import system_info
from convert2rhel.utils import mkdir_p


OPENJDK_RPM_STATE_DIR = "/var/lib/rpm-state/"

logger = logging.getLogger(__name__)


def perform_java_openjdk_workaround():
    if system_info.is_rpm_installed(name="java-1.7.0-openjdk"):
        logger.info(
            "Package java-1.7.0-openjdk found. Applying workaround in"
            "accordance with https://access.redhat.com/solutions/3573891"
        )
        try:
            mkdir_p(OPENJDK_RPM_STATE_DIR)
        except OSError:
            logger.warning(
                "Can't create %s directory." % OPENJDK_RPM_STATE_DIR
            )
        else:
            logger.info("openjdk workaround applied successfully.")


def check_and_resolve():
    perform_java_openjdk_workaround()
