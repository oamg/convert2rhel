import pytest

from envparse import env

from convert2rhel.actions.system_checks.check_firewalld_availability import FIREWALLD_CONFIG_FILE


@pytest.mark.test_firewalld_inhibitor
def test_firewalld_inhibitor(shell, convert2rhel):
    """
    Verify that on the OL8.8 the conversion is inhibited due to
    running firewalld on the system and the `CleanupModulesOnExit` configuration
    option is set to `yes` in firewalld configuration file.
    The reference ticket: https://issues.redhat.com/browse/RHELC-1180
    """
    assert shell("rpm -q firewalld").returncode == 0
    assert shell("systemctl start firewalld").returncode == 0
    assert shell("systemctl enable firewalld").returncode == 0

    assert shell(f"grep 'CleanupModulesOnExit=yes' {FIREWALLD_CONFIG_FILE}").returncode == 0

    with convert2rhel(
        "-y --no-rpm-va --debug --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"), env.str("RHSM_USERNAME"), env.str("RHSM_PASSWORD")
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Pre-conversion analysis report")
        c2r.expect(
            "CHECK_FIREWALLD_AVAILABILITY::FIREWALLD_MODULES_CLEANUP_ON_EXIT_CONFIG",
            timeout=600,
        )

    assert c2r.exitstatus == 1

    assert shell(
        "grep 'Firewalld running on Oracle Linux 8 can lead to a conversion failure' /var/log/convert2rhel/convert2rhel.log"
    )

    # Clean up
    assert shell("systemctl stop firewalld").returncode == 0
    assert shell("systemctl disable firewalld").returncode == 0
