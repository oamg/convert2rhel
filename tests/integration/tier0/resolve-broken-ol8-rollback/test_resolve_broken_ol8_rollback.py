import platform
import sys

import pexpect

from envparse import env


def test_proper_rhsm_clean_up(shell, convert2rhel):
    """Test that c2r does not remove usermod, rhn-setup and os-release during rollback.
    Also checks that the system was succesfully unregistered.
    """

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
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")
        c2r.expect("The tool allows rollback of any action until this point.")
        c2r.sendline("n")
        c2r.expect("Calling command 'subscription-manager unregister'")
        c2r.expect("System unregistered successfully.")

    # check that packages still are in place
    assert shell("rpm -qi usermode").returncode == 0
    assert shell("rpm -qi rhn-setup").returncode == 0
    if "centos-7" in platform.platform():
        assert shell("rpm -qi centos-release").returncode == 0
    elif "centos-8" in platform.platform():
        assert shell("rpm -qi centos-linux-release").returncode == 0
