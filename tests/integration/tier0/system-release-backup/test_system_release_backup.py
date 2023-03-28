import os

import pytest

from conftest import SATELLITE_PKG_DST, SATELLITE_PKG_URL, SYSTEM_RELEASE_ENV
from envparse import env


def assign_repository_variable(repository=None):
    """
    Helper function.
    Assign correct repository setup to install subscription manager from to their respective distribution.
    """

    epel7_repository = "ubi"
    epel8_repository = "baseos"
    if SYSTEM_RELEASE_ENV in ("oracle-7", "centos-7"):
        repository = epel7_repository
    elif "oracle-8" in SYSTEM_RELEASE_ENV or "centos-8" in SYSTEM_RELEASE_ENV:
        repository = epel8_repository

    return repository


BACKUP_DIR = "/tmp/test-backup-release_backup"
BACKUP_DIR_EUS = "%s_eus" % BACKUP_DIR

REPOSITORY = assign_repository_variable()


def prepare_and_install_subscription_manager(shell):
    """
    Preparation phase.
    Remove rhn-client-tools for Oracle Linux 7, disable all repositories and install subscription manager
    from previously set up repository.
    """
    # On Oracle Linux 7 a "rhn-client-tols" package may be present on
    # the system which prevents "subscription-manager" to be installed.
    # Remove package rhn-client-tools from Oracle Linux 7.
    if "oracle-7" in SYSTEM_RELEASE_ENV:
        assert shell("yum remove -y rhn-client-tools")
    assert shell(f"cp files/{REPOSITORY}.repo /etc/yum.repos.d/")
    assert shell(f"yum -y --disablerepo=* --enablerepo={REPOSITORY} install subscription-manager").returncode == 0


def install_katello_package(shell):
    """
    Preparation phase.
    Install katello package for Satellite.
    """
    # OL distros may not have wget installed
    assert shell("yum install wget -y").returncode == 0
    # Install katello package for satellite
    assert (
        shell(
            "wget --no-check-certificate --output-document {} {}".format(SATELLITE_PKG_DST, SATELLITE_PKG_URL)
        ).returncode
        == 0
    )
    assert shell("rpm -i {}".format(SATELLITE_PKG_DST)).returncode == 0


def move_repositories_away(shell):
    """
    Preparation phase.
    Move all repositories to another location, do the same for EUS if applicable.
    """
    # Move all repos to other location, so it is not being used
    shell(f"mkdir {BACKUP_DIR}")
    assert shell(f"mv /etc/yum.repos.d/* {BACKUP_DIR}").returncode == 0

    # EUS version use hardcoded repos from c2r as well
    if "centos-8" in SYSTEM_RELEASE_ENV:
        shell(f"mkdir {BACKUP_DIR_EUS}")
        assert shell(f"mv /usr/share/convert2rhel/repos/* {BACKUP_DIR_EUS}").returncode == 0


def teardown_repositories_and_cleanup(shell):
    """
    Teardown phase.
    Remove changes from the preparation phase.
    """
    # Return repositories to their original location
    assert shell(f"mv {BACKUP_DIR}/* /etc/yum.repos.d/").returncode == 0
    # Return EUS repositories to their original location
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell(f"mv {BACKUP_DIR_EUS}/* /usr/share/convert2rhel/repos/").returncode == 0

    # Remove subscription-manager and associated packages, katello package, custom repositories and backup folder
    assert shell("yum remove -y subscription-manager* katello-*").returncode == 0
    assert shell(f"rm -f {SATELLITE_PKG_DST}").returncode == 0
    assert shell(f"rm -f /etc/yum.repos.d/{REPOSITORY}.repo").returncode == 0
    assert shell(f"rm -rf {BACKUP_DIR}").returncode == 0
    # Install back previously removed client tools
    if "oracle-7" in SYSTEM_RELEASE_ENV:
        shell("yum install -y rhn-client-tools")
        shell("yum remove -y python-syspurpose")
    # The termination of the conversion does not happen fast enough, so same packages can get removed
    # Install the package back to avoid leaving the system in tainted state
    elif "centos-8" in SYSTEM_RELEASE_ENV:
        shell("yum install -y centos-gpg-keys centos-logos")
    # Additionally installing the subscription-manager on Oracle Linux 8, packages librepo and libxml2 get downgraded
    # Update said packages to not interfere with subsequent tests
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        shell("yum update -y librepo libxml2")
        shell("yum install -y oraclelinux-release-el8-* oraclelinux-release-8* redhat-release-8*")


@pytest.mark.test_unsuccessful_satellite_registration
def test_backup_os_release_wrong_registration(shell, convert2rhel):
    """
    Verify that the os-release file is restored when the satellite registration fails.
    Reference issue: RHELC-51
    """
    prepare_and_install_subscription_manager(shell)
    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel("-y --no-rpm-va -k wrong_key -o rUbBiSh_pWd --debug --keep-rhsm") as c2r:
        c2r.expect("Unable to register the system through subscription-manager.")
        c2r.expect("Restore /etc/os-release from backup")

    assert shell("find /etc/os-release").returncode == 0

    # Clean up
    assert shell(f"rm -f /etc/yum.repos.d/{REPOSITORY}.repo").returncode == 0
    assert shell("yum remove -y subscription-manager").returncode == 0
    # Install back problematic ol7 package
    if "oracle-7" in SYSTEM_RELEASE_ENV:
        shell("yum install -y rhn-client-tools")
        shell("yum remove -y python-syspurpose")
    # Update packages downgraded during subman installation
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        shell("yum update -y librepo libxml2")


@pytest.mark.test_missing_system_release
def test_missing_system_release(shell, convert2rhel):
    """
    It is required to have /etc/system-release file present on the system.
    If the file is missing inhibit the conversion.
    """

    # Make backup copy of the file
    backup_folder = "/tmp/missing-system-release_sysrelease_backup/"
    assert shell(f"mkdir {backup_folder}").returncode == 0
    assert shell(f"mv /etc/system-release {backup_folder}").returncode == 0

    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        c2r.expect("Unable to find the /etc/system-release file containing the OS name and version")

    assert c2r.exitstatus != 0

    # Restore the system
    assert shell(f"mv -v {backup_folder}system-release /etc/").returncode == 0
    assert shell(f"rm -rf {backup_folder}").returncode == 0


@pytest.mark.test_backup_os_release_no_envar
def test_backup_os_release_no_envar(shell, convert2rhel):
    """
    This test case removes all the repos on the system which prevents the backup of some files.
    Satellite is being used in all of test cases.
    In this scenario there is no variable `CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK` set.
    This means the conversion is inhibited in early stage.
    """
    # Prepare the system.
    prepare_and_install_subscription_manager(shell)

    install_katello_package(shell)

    move_repositories_away(shell)

    # Since we are moving all repos away, we need to bypass kernel check
    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"

    assert shell("find /etc/os-release").returncode == 0
    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug --keep-rhsm".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("set the environment variable 'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK.")
        assert c2r.exitstatus != 0

    assert shell("find /etc/os-release").returncode == 0

    # Restore system
    teardown_repositories_and_cleanup(shell)
    del os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"]


@pytest.mark.test_backup_os_release_with_envar
def test_backup_os_release_with_envar(shell, convert2rhel):
    """
    In this scenario the variable `CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK` is set.
    This test case removes all the repos on the system and validates that
    the /etc/os-release package is being backed up and restored during rollback.
    Ref ticket: OAMG-5457. Note that after the test, the $releasever
    variable is unset.
    """

    # Prepare the system
    prepare_and_install_subscription_manager(shell)

    install_katello_package(shell)

    move_repositories_away(shell)

    assert shell("find /etc/os-release").returncode == 0

    # Since we are moving all repos away, we need to bypass kernel check
    # We are also setting up the `CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK` envar
    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"
    os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"] = "1"

    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug --keep-rhsm".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        ),
        unregister=True,
    ) as c2r:
        c2r.expect(
            "'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK' environment variable detected, continuing conversion."
        )
        c2r.send(chr(3))
        c2r.sendcontrol("d")

    assert shell("find /etc/os-release").returncode == 0

    # Clean up
    teardown_repositories_and_cleanup(shell)
    del os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"]
    del os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"]
