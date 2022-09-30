import os
import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


def assign_packages(packages=None):
    ol_7_pkgs = ["oracle-release-el7", "usermode", "rhn-setup", "oracle-logos"]
    ol_8_pkgs = ["oraclelinux-release-el8", "usermode", "rhn-setup", "oracle-logos"]
    cos_7_pkgs = ["centos-release", "usermode", "rhn-setup", "python-syspurpose", "centos-logos"]
    cos_8_pkgs = ["centos-linux-release", "usermode", "rhn-setup", "python3-syspurpose", "centos-logos"]
    # The packages 'python-syspurpose' and 'python3-syspurpose' were removed in Oracle Linux 7.9
    # and Oracle Linux 8.2 respectively.
    if "centos-7" in SYSTEM_RELEASE_ENV:
        packages = cos_7_pkgs
    elif "centos-8" in SYSTEM_RELEASE_ENV:
        packages = cos_8_pkgs
    elif "oracle-7" in SYSTEM_RELEASE_ENV:
        packages = ol_7_pkgs
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        packages = ol_8_pkgs

    return packages


def install_packages(shell, packages=None):
    """
    Helper function.
    Install packages that cause trouble/needs to be checked during/after rollback.
    Some packages were removed during the conversion and were not backed up/installed back when the rollback occurred.
    """
    packages_to_remove_at_cleanup = []
    for package in packages:
        if f"{package} is not installed" in shell(f"rpm -q {package}").output:
            print(f"PREP: Setting up {package}")
            assert shell(f"yum install -y {package}").returncode == 0
            packages_to_remove_at_cleanup.append(package)

    return packages_to_remove_at_cleanup


def remove_packages(shell, packages=None):
    """
    Helper function.
    Remove additionally installed packages.
    """
    for package in packages:
        print(f"CLEAN: Removing {package}")
        assert shell(f"yum remove -y {package}").returncode == 0


def is_installed_post_rollback(shell, packages=None):
    """
    Helper function.
    Iterate over list of packages and verify that untracked packages remain installed after the rollback.
    """
    for package in packages:
        print(f"CHECK: Checking for {package}")
        query = shell(f"rpm -q {package}")
        assert f"{package} is not installed" not in query.output


def terminate_and_assert_good_rollback(c2r):
    """
    Helper function.
    Run conversion and terminate it to start the rollback.
    """
    if SYSTEM_RELEASE_ENV in ("oracle-7", "centos-7"):
        # Use 'Ctrl + c' first to check for unexpected behaviour
        # of the rollback feature after process termination
        c2r.sendcontrol("c")
        # Due to inconsistent behaviour of 'Ctrl + c' on some distros
        # use Ctrl + d instead
        c2r.sendcontrol("d")
        # Assert the rollback finished all tasks by going through its last task
        assert c2r.exitstatus != 1
    else:
        c2r.send(chr(3))
        assert c2r.exitstatus != 1

    # Verify the last step of the rollback is present in the log file
    with open("/var/log/convert2rhel/convert2rhel.log", "r") as logfile:
        for line in logfile:
            assert "Rollback: Remove installed RHSM certificate" not in line


@pytest.mark.rhsm_cleanup
def test_proper_rhsm_clean_up(get_system_release, shell, convert2rhel):
    """
    Verify that the system has been successfully unregistered after the rollback.
    Verify that usermode, rhn-setup and os-release packages are not removed.
    """
    prompt_amount = int(os.environ["PROMPT_AMOUNT"])
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages(get_system_release))
    if "oracle" in get_system_release:
        prompt_amount = 3
    # additional question about the removal of python3-syspurpose
    elif "centos" in get_system_release:
        prompt_amount = 4

    with convert2rhel(
        "--serverurl {} --username {} --password {} --pool {} --debug --no-rpm-va".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        while prompt_amount > 0:
            c2r.expect("Continue with the system conversion?")
            c2r.sendline("y")
            prompt_amount -= 1
        c2r.expect("The tool allows rollback of any action until this point.")
        c2r.sendline("n")
        c2r.expect("Calling command 'subscription-manager unregister'")
        c2r.expect("System unregistered successfully.")

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


@pytest.mark.packages_untracked_graceful_rollback
def test_check_untrack_pkgs_graceful(convert2rhel, shell):
    """
    Provide c2r with incorrect username and password, so the registration fails and c2r performs rollback.
    Primary issue - checking for python/3-syspurpose not being removed.
    """
    username = "foo"
    password = "bar"
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())
    with convert2rhel(f"--debug -y --no-rpm-va --username {username} --password {password}") as c2r:
        assert c2r.exitstatus != 0

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


@pytest.mark.packages_untracked_forced_rollback
def test_check_untrack_pkgs_force(convert2rhel, shell):
    """
    Terminate the c2r process forcefully, so the rollback is performed.
    Primary issue - verify that python-syspurpose is not removed.
    """
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())
    with convert2rhel(f"--debug -y --no-rpm-va") as c2r:
        c2r.expect("Username")
        # Due to inconsistent behaviour of 'Ctrl+c'
        # use 'Ctrl+d' instead
        c2r.sendcontrol("d")
        assert c2r.exitstatus != 0

    is_installed_post_rollback(shell, assign_packages(get_system_release))
    remove_packages(shell, packages_to_remove_at_cleanup)


@pytest.mark.terminate_on_registration
def test_terminate_registration_start(convert2rhel):
    """
    Send termination signal immediately after c2r tries the registration.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel(
        "--debug -y --no-rpm-va --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Registering the system using subscription-manager")
        terminate_and_assert_good_rollback(c2r)


@pytest.mark.terminate_on_username
def test_terminate_on_username_prompt(convert2rhel):
    """
    Send termination signal on the user prompt for username.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel("--debug -y --no-rpm-va") as c2r:
        c2r.expect("Username:")
        terminate_and_assert_good_rollback(c2r)


@pytest.mark.terminate_on_password
def test_terminate_on_password_prompt(convert2rhel, get_system_release):
    """
    Send termination signal on the user prompt for password.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel("--debug -y --no-rpm-va --username {}".format(env.str("RHSM_USERNAME"))) as c2r:
        c2r.expect("Password:")
        terminate_and_assert_good_rollback(c2r)


@pytest.mark.terminate_on_subscription
def test_terminate_on_subscription_prompt(convert2rhel):
    """
    Send termination signal on the user prompt for subscription number.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel(
        "--debug -y --no-rpm-va --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Enter number of the chosen subscription:")
        terminate_and_assert_good_rollback(c2r)
