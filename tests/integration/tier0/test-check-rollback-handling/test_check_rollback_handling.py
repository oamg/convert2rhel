import os
import platform

from envparse import env


def test_proper_rhsm_clean_up(shell, convert2rhel):
    """Test that c2r does not remove usermod, rhn-setup and os-release during rollback.
    Also checks that the system was successfully unregistered.
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


def assert_not_installed(shell, pkg=""):
    # Checks if untracked package stays installed
    query = shell(f"rpm -q {pkg}")
    try:
        assert f"{pkg} is not installed" not in query.output
    except AssertionError:
        # Install the package (if missing) back
        # to not misrepresent results of other tests
        os.system(f"yum install -y {pkg}")
        raise


def test_check_untrack_pkgs_graceful(convert2rhel, shell):
    username = "foo"
    password = "bar"
    # Provide c2r with incorrect username and password,
    # so it fails the registration and performs rollback.
    with convert2rhel(f"-y --no-rpm-va --username {username} --password {password}") as c2r:
        assert c2r.exitstatus != 0
    if "centos-8" in platform.platform():
        assert_not_installed(shell, "python3-syspurpose")
    elif "oracle-7" in platform.platform():
        assert_not_installed(shell, "oracle-logos")


def test_check_untrack_pkgs_force(convert2rhel, shell):
    # Terminate the c2r process forcefully,
    # so it performs rollback.
    with convert2rhel(f"-y --no-rpm-va") as c2r:
        c2r.expect("Username")
        # Due to inconsistent behaviour of 'Ctrl+c'
        # use 'Ctrl+d' instead
        c2r.sendcontrol("d")
        assert c2r.exitstatus != 0
    if "centos-8" in platform.platform():
        assert_not_installed(shell, "python3-syspurpose")
    elif "oracle-7" in platform.platform():
        assert_not_installed(shell, "oracle-logos")
