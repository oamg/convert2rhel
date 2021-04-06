import logging

from convert2rhel.systeminfo import system_info
from convert2rhel.utils import mkdir_p


OPENJDK_RPM_STATE_DIR = "/var/lib/rpm-state/"

logger = logging.getLogger(__name__)


def perform_java_openjdk_workaround():
    """Resolve a yum transaction failure on CentOS/OL 6 related to the java-1.7.0-openjdk package.

    The java-1.7.0-openjdk package expects that the /var/lib/rpm-state/ directory is present. Yet, it may be missing.
    This directory is supposed to be created by the copy-jdk-configs package during the system installation, but it does
    not do that: https://bugzilla.redhat.com/show_bug.cgi?id=1620053#c14.

    If the original system has an older version of copy-jdk-configs installed than the one available in RHEL repos, the
    issue does not occur because the copy-jdk-configs is updated together with the java-1.7.0-openjdk package and a
    pretrans script of the copy-jdk-configs creates the dir.

    In case there's no newer version of copy-jdk-configs available in RHEL but a newer version of java-1.7.0-openjdk is
    available, we need to create the /var/lib/rpm-state/ directory as suggested in
    https://access.redhat.com/solutions/3573891.
    """

    logger.info("Checking if java-1.7.0-openjdk is installed.")
    if system_info.is_rpm_installed(name="java-1.7.0-openjdk"):
        logger.info(
            "Package java-1.7.0-openjdk found. Applying workaround in"
            "accordance with https://access.redhat.com/solutions/3573891"
        )
        try:
            mkdir_p(OPENJDK_RPM_STATE_DIR)
        except OSError:
            logger.warning(
                "Unable to create the %s directory." % OPENJDK_RPM_STATE_DIR
            )
        else:
            logger.info("openjdk workaround applied successfully.")
    else:
        logger.info("java-1.7.0-openjdk not installed.")


def check_and_resolve():
    perform_java_openjdk_workaround()
