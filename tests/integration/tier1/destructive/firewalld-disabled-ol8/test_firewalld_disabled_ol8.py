import os

import pytest

from envparse import env

from convert2rhel.actions.system_checks.check_firewalld_availability import FIREWALLD_CONFIG_FILE


@pytest.mark.test_firewalld_disabled
def test_firewalld_disabled_ol8(shell, convert2rhel):
    """
    Verify that when the firewalld is not running and the configuration option has
    default value, the conversion can proceed without problems on Oracle-Linux 8.8.
    The reference ticket: https://issues.redhat.com/browse/RHELC-1180
    """
    if not os.path.exists(FIREWALLD_CONFIG_FILE):
        pytest.fail("Firewalld configuration file does not exist")

    assert shell("systemctl stop firewalld").returncode == 0
    assert shell("systemctl disable firewalld").returncode == 0

    shell(f"sed -i 's/CleanupModulesOnExit=no/CleanupModulesOnExit=yes/g' {FIREWALLD_CONFIG_FILE}")

    with convert2rhel(
        "-y --no-rpm-va --debug --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"), env.str("RHSM_USERNAME"), env.str("RHSM_PASSWORD")
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Firewalld service reported that it is not running.")

    assert c2r.exitstatus == 0

    # There should not be any problems
    assert shell("grep -i 'traceback' /var/log/convert2rhel/convert2rhel.log").returncode == 1
