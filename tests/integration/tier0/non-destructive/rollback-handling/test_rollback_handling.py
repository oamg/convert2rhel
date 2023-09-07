import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


def assign_packages(packages=None):
    # If nothing was passed down to packages, set it to an empty list
    if not packages:
        packages = []

    ol_7_pkgs = ["oracle-release-el7", "usermode", "rhn-setup", "oracle-logos"]
    ol_8_pkgs = ["oraclelinux-release-el8", "usermode", "rhn-setup", "oracle-logos"]
    cos_7_pkgs = ["centos-release", "usermode", "rhn-setup", "python-syspurpose", "centos-logos"]
    cos_8_pkgs = ["centos-linux-release", "usermode", "rhn-setup", "python3-syspurpose", "centos-logos"]
    # The packages 'python-syspurpose' and 'python3-syspurpose' were removed in Oracle Linux 7.9
    # and Oracle Linux 8.2 respectively.
    if "centos-7" in SYSTEM_RELEASE_ENV:
        packages += cos_7_pkgs
    elif "centos-8" in SYSTEM_RELEASE_ENV:
        packages += cos_8_pkgs
    elif "oracle-7" in SYSTEM_RELEASE_ENV:
        packages += ol_7_pkgs
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        packages += ol_8_pkgs

    return packages


def install_packages(shell, packages):
    """
    Helper function.
    Install packages that cause trouble/needs to be checked during/after rollback.
    Some packages were removed during the conversion and were not backed up/installed back when the rollback occurred.
    """
    packages_to_remove_at_cleanup = []
    for package in packages:
        if f"{package} is not installed" in shell(f"rpm -q {package}").output:
            packages_to_remove_at_cleanup.append(package)

    # Run this only once as package managers take too long to figure out
    # dependencies and install the packages.
    print(f"PREP: Setting up {','.join(packages_to_remove_at_cleanup)}")
    if packages_to_remove_at_cleanup:
        assert shell(f"yum install -y {' '.join(packages_to_remove_at_cleanup)}").returncode == 0
    return packages_to_remove_at_cleanup


def remove_packages(shell, packages):
    """
    Helper function.
    Remove additionally installed packages.
    """
    if not packages:
        return

    print(f"CLEAN: Removing {','.join(packages)}")
    assert shell(f"yum remove -y {' '.join(packages)}").returncode == 0


def is_installed_post_rollback(shell, packages):
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
    # Use 'Ctrl + c' first to check for unexpected behaviour
    # of the rollback feature after process termination
    c2r.sendcontrol("c")

    # Assert the rollback finished all tasks by going through its last task
    c2r.expect("Rollback: Remove installed certificate", timeout=120)


@pytest.mark.test_rhsm_cleanup
def test_proper_rhsm_clean_up(shell, convert2rhel):
    """
    Verify that the system has been successfully unregistered after the rollback.
    Verify that usermode, rhn-setup and os-release packages are not removed.
    Verify that python-syspurpose is not removed.
    """
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())

    with convert2rhel(
        "--serverurl {} --username {} --password {} --pool {} --debug --no-rpm-va".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Wait till the system is properly registered and subscribed, then
        # send the interrupt signal to the c2r process.
        c2r.expect("Convert: Get RHEL repository IDs")
        c2r.sendcontrol("c")

        c2r.expect("Calling command 'subscription-manager unregister'", timeout=120)
        c2r.expect("System unregistered successfully.", timeout=120)

    assert c2r.exitstatus != 0

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


@pytest.mark.test_missing_credentials_rollback
def test_missing_credentials_rollback(convert2rhel, shell):
    """
    The credentials are omitted during the call of convert2rhel. This results in
    a failure - system is expected to be subscribed.
    Verify that the resulted rollback behaves correctly.
    """
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())

    with convert2rhel("--debug -y --no-rpm-va") as c2r:
        c2r.expect_exact("ERROR - (ERROR) SUBSCRIBE_SYSTEM::SYSTEM_NOT_REGISTERED")

    assert c2r.exitstatus != 0

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


@pytest.mark.test_packages_untracked_graceful_rollback
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


@pytest.mark.test_terminate_on_registration_start
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
    assert c2r.exitstatus != 0


@pytest.mark.skip(reason="SIGINT is sent too soon which breaks the rollback")
@pytest.mark.test_terminate_on_registration_success
def test_terminate_registration_success(convert2rhel):
    """
    Send termination signal immediately after c2r successfully finishes the registration.
    Verify that c2r goes successfully through the rollback.
    Verify that the subscription is auto-attached.
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
        c2r.expect("System registration succeeded.", timeout=180)
        # Verify auto-attachment of the subscription
        c2r.expect("Auto-attaching compatible subscriptions to the system ...", timeout=180)
        c2r.expect("DEBUG - Calling command 'subscription-manager attach --auto'", timeout=180)
        c2r.expect("Status:       Subscribed", timeout=180)
        # TODO [mlitwora]: If the SIGINT is sent right after the Status: Subscribed, then the system ends up in broken stat
        # that makes another c2r unsuccessful. Waiting little bit longer fixes the problem but probably makes the
        # test "useless".
        # c2r.expect("Convert: Get RHEL repository IDs")
        terminate_and_assert_good_rollback(c2r)
    assert c2r.exitstatus != 0
