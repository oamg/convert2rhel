import platform

from envparse import env


booted_os = platform.platform()
OL_7_PKGS = ["oracle-release-el7", "usermode", "rhn-setup", "oracle-logos"]
OL_8_PKGS = ["oracle-release-el8", "usermode", "rhn-setup", "oracle-logos"]
COS_7_PKGS = ["centos-release", "usermode", "rhn-setup", "python-syspurpose", "centos-logos"]
COS_8_PKGS = ["centos-linux-release", "usermode", "rhn-setup", "python3-syspurpose", "centos-logos"]
# The packages 'python-syspurpose' and 'python3-syspurpose' were removed in Oracle Linux 7.9
# and Oracle Linux 8.2 respectively.


def install_pkg(shell, pkgs=None):
    if "centos-7" in booted_os:
        pkgs = COS_7_PKGS
    elif "centos-8" in booted_os:
        pkgs = COS_8_PKGS
    elif "oracle-7" in booted_os:
        pkgs = OL_7_PKGS
    elif "oracle-8" in booted_os:
        pkgs = OL_8_PKGS
    for pkg in pkgs:
        print(f"PREP: Setting up {pkg}")
        assert shell(f"yum install -y {pkg}").returncode == 0


def is_installed(shell, pkgs=None):
    # Iterate over given packages and check if untracked packages stay installed.
    for pkg in pkgs:
        print(f"CHECK: Checking for {pkg}")
        query = shell(f"rpm -q {pkg}")
        assert f"{pkg} is not installed" not in query.output


def post_rollback_check(shell):
    if "centos-7" in booted_os:
        is_installed(shell, COS_7_PKGS)
    elif "centos-8" in booted_os:
        is_installed(shell, COS_8_PKGS)
    elif "oracle-7" in booted_os:
        is_installed(shell, OL_7_PKGS)
    elif "oracle-8" in booted_os:
        is_installed(shell, OL_8_PKGS)


def terminate_and_assert_good_rollback(c2r):
    if "oracle-7" in booted_os or "centos-7" in booted_os:
        # Use 'Ctrl + c' first to check for unexpected behaviour
        # of the rollback feature after process termination
        c2r.sendcontrol("c")
        # Due to inconsistent behaviour of 'Ctrl + c' on some distros
        # use Ctrl + d instead
        c2r.sendcontrol("d")
        # Assert the rollback finished all tasks by going through its last task
        assert c2r.expect("Rollback: Removing installed RHSM certificate") == 0
        assert c2r.exitstatus != 1
    else:
        c2r.sendcontrol("c")
        assert c2r.expect("Rollback: Removing installed RHSM certificate") == 0
        assert c2r.exitstatus != 1


def test_proper_rhsm_clean_up(shell, convert2rhel):
    # Primary issue - checking for usermode, rhn-setup and os-release.
    # It also checks that the system has been successfully unregistered.
    install_pkg(shell)

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

    post_rollback_check(shell)


def test_check_untrack_pkgs_graceful(convert2rhel, shell):
    # Provide c2r with incorrect username and password,
    # so the registration fails and c2r performs rollback.
    # Primary issue - checking for python/3-syspurpose not being removed.
    username = "foo"
    password = "bar"
    install_pkg(shell)
    with convert2rhel(f"-y --no-rpm-va --username {username} --password {password}") as c2r:
        assert c2r.exitstatus != 0

    post_rollback_check(shell)


def test_check_untrack_pkgs_force(convert2rhel, shell):
    # Terminate the c2r process forcefully, so the rollback is performed.
    # Primary issue - checking for python/3-syspurpose not being removed.
    install_pkg(shell)
    with convert2rhel(f"-y --no-rpm-va") as c2r:
        c2r.expect("Username")
        # Due to inconsistent behaviour of 'Ctrl+c'
        # use 'Ctrl+d' instead
        c2r.sendcontrol("d")
        assert c2r.exitstatus != 0

    post_rollback_check(shell)


def test_terminate_registration_start(convert2rhel):
    # Send termination signal immediately after c2r tries the registration.
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {}").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        )
    ) as c2r:
        c2r.expect("Registering the system using subscription-manager")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_username_prompt(convert2rhel):
    # Send termination signal on the user prompt for Username.
    with convert2rhel("-y --no-rpm-va") as c2r:
        c2r.expect("Username:")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_password_prompt(convert2rhel):
    # Send termination signal on the user prompt for Password.
    with convert2rhel(("-y --no-rpm-va --username {}").format(env.str("RHSM_USERNAME"))) as c2r:
        c2r.expect("Password:")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_subscription_prompt(convert2rhel):
    # Send termination signal on the user prompt Subscription version.
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {}").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        )
    ) as c2r:
        c2r.expect("Enter number of the chosen subscription:")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_organization_prompt(convert2rhel):
    # Send termination signal on the user prompt for Organization.
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} -k {}").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_KEY"),
        )
    ) as c2r:
        c2r.expect("Organization:")
        terminate_and_assert_good_rollback(c2r)


def test_terminate_on_pool_prompt(convert2rhel):
    # Send termination signal on each user prompt asking about continuation.
    # There is one less prompt on Oracle Linux 8 and CentOS 7
    if "oracle-8" in booted_os or "centos-7" in booted_os:
        prompt_count = 2
    else:
        prompt_count = 3
    for i in range(prompt_count):
        with convert2rhel(
            ("--serverurl {} --username {} --password {} --pool {} --debug --no-rpm-va").format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ) as c2r:
            if i == 0:
                c2r.expect("Continue with the system conversion?")
                terminate_and_assert_good_rollback(c2r)
            elif i == 1:
                c2r.expect("Continue with the system conversion?")
                c2r.sendline("y")
                c2r.expect("Continue with the system conversion?")
                terminate_and_assert_good_rollback(c2r)
            elif i == 2:
                for n in range(1):
                    c2r.expect("Continue with the system conversion?")
                    c2r.sendline("y")
                c2r.expect("Continue with the system conversion?")
                terminate_and_assert_good_rollback(c2r)
            elif i == 3:
                for n in range(2):
                    c2r.expect("Continue with the system conversion?")
                    c2r.sendline("y")
                c2r.expect("The tool allows rollback of any action until this point.")
                c2r.expect("Continue with the system conversion?")
                terminate_and_assert_good_rollback(c2r)
