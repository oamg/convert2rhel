import pytest


@pytest.mark.test_firewalld_inhibitor
def test_firewalld_inhibitor(shell, convert2rhel):
    """
    Verify that on the OL8.8 the conversion is inhibited due to
    running firewalld on the system.
    The reference ticket: https://issues.redhat.com/browse/RHELC-1180
    """
    assert shell("rpm -q firewalld").returncode == 0
    assert shell("systemctl start firewalld").returncode == 0
    assert shell("systemctl enable firewalld").returncode == 0

    with convert2rhel("-y --no-rpm-va --debug", unregister=True) as c2r:
        c2r.expect(
            "CHECK_FIREWALLD_AVAILABILITY::FIREWALLD_DAEMON_RUNNING - Firewalld is running",
            timeout=600,
        )

    assert c2r.exitstatus == 1

    # Clean up
    assert shell("systemctl stop firewalld").returncode == 0
    assert shell("systemctl disable firewalld").returncode == 0
