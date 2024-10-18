import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS, SystemInformationRelease


@pytest.fixture(autouse=True)
def backup_removal(shell):
    """
    Fixture to remove all backed up files from
    /var/lib/convert2rhel/backup/
    /usr/share/convert2rhel/subscription-manager/
    """
    dirs_to_clear = ["/usr/share/convert2rhel/subscription-manager/", "/var/lib/convert2rhel/backup/"]
    for directory in dirs_to_clear:
        shell(f"rm -rf {directory}*")

    yield


def assign_packages():
    """
    Helper function.
    Assign packages to be installed and/or validated.
    """
    os_distribution = SystemInformationRelease.distribution
    os_version = SystemInformationRelease.version.major

    os_key = f"{os_distribution}-{os_version}" if os_distribution == "centos" else os_distribution

    release_mapping = {
        "centos-7": ["centos-release", "centos-logos"],
        "centos-8": ["centos-linux-release", "centos-logos"],
        "oracle": [f"oraclelinux-release-el{os_version}", "oracle-logos"],
        "almalinux": ["almalinux-release", "almalinux-logos"],
        "rocky": ["rocky-release", "rocky-logos"],
        "stream": ["centos-stream-release", "centos-logos"],
    }

    python_ver = "3" if os_version > 7 else ""

    packages = release_mapping.get(os_key, []) + ["usermode"]
    # The packages 'python-syspurpose' and 'python3-syspurpose' were removed in Oracle Linux 7.9
    # and Oracle Linux 8.2 respectively, the package is also not present in EL9 systems, same as the rhn-setup
    if os_distribution != "oracle" and os_version != 9:
        packages.extend(["rhn-setup", f"python{python_ver}-syspurpose"])

    return packages


def install_packages(shell, packages):
    """
    Helper function.
    Install packages that cause trouble/needs to be checked during/after rollback.
    Some packages were removed during the conversion and were not backed up/installed back when the rollback occurred.
    """
    packages_to_remove_at_cleanup = []
    for package in packages:
        is_installed = shell(f"rpm -q {package}").returncode
        if is_installed == 1:
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
        is_installed = shell(f"rpm -q {package}").returncode
        # rpm -q command returns 0 when package is installed, returns 1 otherwise
        assert is_installed == 0


def terminate_and_assert_good_rollback(c2r):
    """
    Helper function.
    Run conversion and terminate it to start the rollback.
    """
    # Use 'Ctrl + c' to check for unexpected behaviour
    # of the rollback feature after process termination
    c2r.sendcontrol("c")

    # Assert the rollback finished all tasks by going through its last task
    c2r.expect("Rollback: Remove installed certificate", timeout=120)


@pytest.fixture
def yum_plugin_local(shell):
    """
    Fixture to install and remove yum-plugin-local.
    """
    command = "yum install -y yum-plugin-local"
    if "oracle-7" in SYSTEM_RELEASE_ENV:
        command += " --enablerepo=ol7_optional_latest"
    assert shell(command).returncode == 0

    yield

    assert shell("yum remove -y yum-plugin-local").returncode == 0


@pytest.fixture
def immutable_os_release_file(shell):
    """
    Fixture to set the os-release file as immutable.
    """
    shell("chattr +i $(realpath /etc/os-release)")

    yield

    # Because on CentOS7 the /etc/os-release is a symlink and
    # after the failed rollback the symlink is not restored.
    # Yum is not able to handle this (on dnf systems it is not an issue).
    if SYSTEM_RELEASE_ENV in ("centos-7", "stream-9-latest"):
        shell("chattr -i /usr/lib/os-release")
        shell("rm -f /etc/os-release")
    else:
        shell("chattr -i $(realpath /etc/os-release)")


def test_polluted_yumdownloader_output_by_yum_plugin_local(shell, convert2rhel, yum_plugin_local):
    """
    Verify that the yumdownloader output in the backup packages task is parsed correctly.
    In this scenario the yum-plugin-local was causing that excluded packages were not detected as downloaded during
    a backup. Then, the removed excluded packages were not installed back during a rollback (RHELC-1272).
    Verify the utility handles both - packages downloaded for the backup
    and packages already existing in the backup directory.
    """
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())

    # Run the utility second time to verify the backup works
    # even with the packages already backed up
    for run in range(2):
        with convert2rhel("analyze --debug -y") as c2r:
            c2r.expect("Rollback: Install removed packages")
            c2r.expect("Pre-conversion analysis report", timeout=600)

        is_installed_post_rollback(shell, assign_packages())

    remove_packages(shell, packages_to_remove_at_cleanup)


def test_proper_rhsm_clean_up(shell, convert2rhel):
    """
    Verify that the system has been successfully unregistered after the rollback.
    Verify that usermode, rhn-setup and os-release packages are not removed.
    Verify that python-syspurpose is not removed.
    """
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())

    with convert2rhel(
        "analyze --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Wait till the system is properly registered and subscribed, then
        # send the interrupt signal to the c2r process.
        c2r.expect("Prepare: Get RHEL repository IDs")
        c2r.sendcontrol("c")

        c2r.expect("Calling command 'subscription-manager unregister'", timeout=120)
        c2r.expect("System unregistered successfully.", timeout=120)

    assert c2r.exitstatus == 1

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


def test_missing_credentials_rollback(convert2rhel, shell):
    """
    The credentials are omitted during the call of convert2rhel. This results in
    a failure - system is expected to be subscribed.
    Verify that the resulted rollback behaves correctly.
    """
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())

    with convert2rhel("--debug -y") as c2r:
        c2r.expect_exact("ERROR - (ERROR) SUBSCRIBE_SYSTEM::SYSTEM_NOT_REGISTERED")

    assert c2r.exitstatus == 2

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


def test_packages_untracked_graceful_rollback(convert2rhel, shell):
    """
    Provide c2r with incorrect username and password, so the registration fails and c2r performs rollback.
    Primary issue - checking for python/3-syspurpose not being removed.
    """
    username = "foo"
    password = "bar"
    packages_to_remove_at_cleanup = install_packages(shell, assign_packages())
    with convert2rhel(f"--debug -y --username {username} --password {password}") as c2r:
        pass
    assert c2r.exitstatus == 2

    is_installed_post_rollback(shell, assign_packages())
    remove_packages(shell, packages_to_remove_at_cleanup)


def test_terminate_on_registration_start(convert2rhel):
    """
    Send termination signal immediately after c2r tries the registration.
    Verify that c2r goes successfully through the rollback.
    """
    with convert2rhel(
        "--debug -y --serverurl {} --username {} --password {}".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Registering the system using subscription-manager")
        terminate_and_assert_good_rollback(c2r)
    assert c2r.exitstatus == 1


@pytest.mark.skip(reason="SIGINT is sent too soon which breaks the rollback")
def test_terminate_on_registration_success(convert2rhel):
    """
    Send termination signal immediately after c2r successfully finishes the registration.
    Verify that c2r goes successfully through the rollback.
    Verify that the subscription is auto-attached.
    """
    with convert2rhel(
        "--debug -y --serverurl {} --username {} --password {}".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("Registering the system using subscription-manager")
        c2r.expect("System registration succeeded.", timeout=180)
        # Verify auto-attachment of the subscription
        c2r.expect("Auto-attaching compatible subscriptions to the system ...", timeout=180)
        c2r.expect("DEBUG - Calling command 'subscription-manager attach --auto'", timeout=180)
        c2r.expect("Status:       Subscribed", timeout=180)
        terminate_and_assert_good_rollback(c2r)
    assert c2r.exitstatus == 1


@pytest.mark.parametrize("c2r_mode", ["analyze", "convert"])
def test_rollback_failure_returncode(shell, convert2rhel, immutable_os_release_file, c2r_mode):
    """
    Make os-release file immutable. This will cause the conversion rollback to fail (https://issues.redhat.com/browse/RHELC-1248).
    Verify that the analysis and conversion ends with exit code 1 respecting the failure (https://issues.redhat.com/browse/RHELC-1275).
    Use fake credentials to cause the inhibition.
    """

    with convert2rhel("{} --debug -y --username happy_hippo --password hippo_is_hungry".format(c2r_mode)) as c2r:
        c2r.expect("WARNING - Error while rolling back")
        c2r.expect("CRITICAL - Rollback of system wasn't completed successfully.")
    assert c2r.exitstatus == 1
