import os

import pytest

from envparse import env

from convert2rhel.actions.system_checks.check_firewalld_availability import FIREWALLD_CONFIG_FILE


@pytest.mark.test_firewalld_config
def test_firewalld_config_ol8(shell, convert2rhel):
    """
    Verify that properly changing the firewalld configuration file
    allows to convert the system without any issue.
    The reference ticket: https://issues.redhat.com/browse/RHELC-1180
    """
    if not os.path.exists(FIREWALLD_CONFIG_FILE):
        pytest.fail("Firewalld configuration file does not exist")

    assert shell("systemctl start firewalld").returncode == 0
    assert shell("systemctl enable firewalld").returncode == 0

    assert (
        shell(f"sed -i 's/CleanupModulesOnExit=yes/CleanupModulesOnExit=no/g' {FIREWALLD_CONFIG_FILE}").returncode == 0
    )

    assert shell("firewall-cmd --reload").returncode == 0
    with convert2rhel(
        "-y --no-rpm-va --debug --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"), env.str("RHSM_USERNAME"), env.str("RHSM_PASSWORD")
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Pre-conversion analysis report")
        c2r.expect_exact("(WARNING) CHECK_FIREWALLD_AVAILABILITY::FIREWALLD_IS_RUNNING")

    assert c2r.exitstatus == 0

    # There should not be any problems
    assert shell("grep -i 'traceback' /var/log/convert2rhel/convert2rhel.log").returncode == 1
