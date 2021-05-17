import sys

import pexpect

from envparse import env


def test_proper_rhsm_clean_up(shell, convert2rhel):
    """Test that c2r does not remove usermod and rhn-setup during rollback."""

    # Ensure usermode and rhn-setup packages are presented
    assert shell("yum install -y usermode rhn-setup").returncode == 0

    # run c2r until subscribing the system and then emulate pressing Ctrl + C
    with convert2rhel(
        ("--serverurl {} --username {} --password {} --pool {} --debug --no-rpm-va").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        c2r.expect("Building subscription-manager command")
        # send Ctrl-C
        c2r.send(chr(3))

    # check that packages still are in place
    assert shell("rpm -qi usermode").returncode == 0
    assert shell("rpm -qi rhn-setup").returncode == 0
