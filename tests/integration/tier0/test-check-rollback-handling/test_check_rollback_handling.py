import os

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


OL_7_PKGS = ["oracle-release-el7", "usermode", "rhn-setup", "oracle-logos"]
OL_8_PKGS = ["oraclelinux-release-el8", "usermode", "rhn-setup", "oracle-logos"]
COS_7_PKGS = ["centos-release", "usermode", "rhn-setup", "python-syspurpose", "centos-logos"]
COS_8_PKGS = ["centos-linux-release", "usermode", "rhn-setup", "python3-syspurpose", "centos-logos"]
# The packages 'python-syspurpose' and 'python3-syspurpose' were removed in Oracle Linux 7.9
# and Oracle Linux 8.2 respectively.


def install_pkg(shell, pkgs=None):
    """
    Helper function.
    Install packages that cause trouble/needs to be checked during/after rollback.
    Some packages were removed during the conversion and were not backed up/installed back when the rollback occurred.
    """
    if "centos-7" in SYSTEM_RELEASE_ENV:
        pkgs = COS_7_PKGS
    elif "centos-8" in SYSTEM_RELEASE_ENV:
        pkgs = COS_8_PKGS
    elif "oracle-7" in SYSTEM_RELEASE_ENV:
        pkgs = OL_7_PKGS
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        pkgs = OL_8_PKGS
    for pkg in pkgs:
        print(f"PREP: Setting up {pkg}")
        assert shell(f"yum install -y {pkg}").returncode == 0


def is_installed(shell, pkgs=None):
    """
    Helper function.
    Iterate over list of packages and verify that untracked packages stay installed after the rollback.
    """
    for pkg in pkgs:
        print(f"CHECK: Checking for {pkg}")
        query = shell(f"rpm -q {pkg}")
        assert f"{pkg} is not installed" not in query.output


def post_rollback_check(shell):
    """
    Helper function.
    Provide respective packages to the is_installed() helper function.
    """
    if "centos-7" in SYSTEM_RELEASE_ENV:
        is_installed(shell, COS_7_PKGS)
    elif "centos-8" in SYSTEM_RELEASE_ENV:
        is_installed(shell, COS_8_PKGS)
    elif "oracle-7" in SYSTEM_RELEASE_ENV:
        is_installed(shell, OL_7_PKGS)
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        is_installed(shell, OL_8_PKGS)


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
        c2r.sendcontrol("c")
        assert c2r.exitstatus != 1

    # Verify the last step of the rollback is present in the log file
    with open("/var/log/convert2rhel/convert2rhel.log", "r") as logfile:
        for line in logfile:
            assert "Rollback: Removing installed RHSM certificate" not in line


def test_proper_rhsm_clean_up(shell, convert2rhel):
    """
    Verify that the system has been successfully unregistered after the rollback.
    Verify that usermode, rhn-setup and os-release packages are not removed.
    """
    install_pkg(shell)
    prompt_amount = int(os.environ["PROMPT_AMOUNT"])
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

    post_rollback_check(shell)


def test_check_untrack_pkgs_graceful(convert2rhel, shell):
    """
    Provide c2r with incorrect username and password, so the registration fails and c2r performs rollback.
    Primary issue - checking for python/3-syspurpose not being removed.
    """
    username = "foo"
    password = "bar"
    install_pkg(shell)
    with convert2rhel(f"-y --no-rpm-va --username {username} --password {password}") as c2r:
        assert c2r.exitstatus != 0

    post_rollback_check(shell)


def test_check_untrack_pkgs_force(convert2rhel, shell):
    """
    Terminate the c2r process forcefully, so the rollback is performed.
    Primary issue - verify that python-syspurpose is not removed.
    """
    install_pkg(shell)
    with convert2rhel(f"-y --no-rpm-va") as c2r:
        c2r.expect("Username")
        # Due to inconsistent behaviour of 'Ctrl+c'
        # use 'Ctrl+d' instead
        c2r.sendcontrol("d")
        assert c2r.exitstatus != 0

    post_rollback_check(shell)


def test_terminate_registration_start(convert2rhel):
    """
    Send termination signal immediately after c2r tries the registration.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        )
    ) as c2r:
        c2r.expect("Registering the system using subscription-manager")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_username_prompt(convert2rhel):
    """
    Send termination signal on the user prompt for username.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel("-y --no-rpm-va") as c2r:
        c2r.expect("Username:")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_password_prompt(convert2rhel):
    """
    Send termination signal on the user prompt for password.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel("-y --no-rpm-va --username {}".format(env.str("RHSM_USERNAME"))) as c2r:
        c2r.expect("Password:")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_subscription_prompt(convert2rhel):
    """
    Send termination signal on the user prompt for subscription number.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {}".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        )
    ) as c2r:
        c2r.expect("Enter number of the chosen subscription:")
        terminate_and_assert_good_rollback(c2r)
