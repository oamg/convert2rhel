import re

import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


@pytest.fixture(scope="function")
def custom_subman(shell, repository=None):
    """ """
    # Setup repositories to install the subscription-manager from.
    epel7_repository = "ubi"
    epel8_repository = "baseos"
    if re.match(r"^(centos|oracle)-7$", SYSTEM_RELEASE_ENV):
        repository = epel7_repository
    elif re.match(r"^(centos|oracle|alma|rocky)-8", SYSTEM_RELEASE_ENV):
        repository = epel8_repository

    # On Oracle Linux 7 a "rhn-client-tools" package may be present on
    # the system which prevents "subscription-manager" to be installed.
    # Remove package rhn-client-tools from Oracle Linux 7.
    if "oracle-7" in SYSTEM_RELEASE_ENV:
        assert shell("yum remove -y rhn-client-tools")
    assert shell(f"cp files/{repository}.repo /etc/yum.repos.d/")
    # Install subscription-manager from 'custom' repositories, disable others for the transaction.
    assert shell(f"yum -y --disablerepo=* --enablerepo={repository} install subscription-manager").returncode == 0

    yield

    # Remove custom subscription-manager
    assert shell(f"yum remove -y --disablerepo=* --enablerepo={repository} subscription-manager*").returncode == 0
    assert shell(f"rm -f /etc/yum.repos.d/{repository}.repo").returncode == 0

    # Some packages might get downgraded during the setup; update just to be sure the system is fine
    shell("yum update -y")


@pytest.mark.test_unsuccessful_satellite_registration
def test_backup_os_release_wrong_registration(shell, convert2rhel, custom_subman):
    """
    Verify that the os-release file is restored when the satellite registration fails.
    Reference issue: RHELC-51
    """
    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel("-y -k wrong_key -o rUbBiSh_pWd --debug") as c2r:
        c2r.expect("Unable to register the system through subscription-manager.")
        c2r.expect("Restore /etc/os-release from backup")

    assert c2r.exitstatus != 0

    assert shell("find /etc/os-release").returncode == 0


@pytest.fixture(scope="function")
def system_release_missing(shell):

    # Make backup copy of the file
    backup_folder = "/tmp/missing-system-release_sysrelease_backup/"
    assert shell(f"mkdir {backup_folder}").returncode == 0
    assert shell(f"mv -v /etc/system-release {backup_folder}").returncode == 0

    yield

    # Restore the system
    assert shell(f"mv -v {backup_folder}system-release /etc/").returncode == 0
    assert shell(f"rm -rf -v {backup_folder}").returncode == 0


@pytest.mark.test_missing_system_release
def test_missing_system_release(shell, convert2rhel, system_release_missing):
    """
    It is required to have /etc/system-release file present on the system.
    If the file is missing inhibit the conversion.
    """
    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        )
    ) as c2r:
        c2r.expect("Unable to find the /etc/system-release file containing the OS name and version")

    assert c2r.exitstatus != 0


@pytest.mark.test_backup_os_release_no_envar
def test_backup_os_release_no_envar(shell, convert2rhel, custom_subman, satellite_registration, remove_repositories):
    """
    This test case removes all the repos on the system which prevents the backup of some files.
    Satellite is being used in all of test cases.
    In this scenario there is no variable `CONVERT2RHEL_INCOMPLETE_ROLLBACK` set.
    This means the conversion is inhibited in early stage.
    """

    assert shell("find /etc/os-release").returncode == 0
    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("set the environment variable 'CONVERT2RHEL_INCOMPLETE_ROLLBACK")
        assert c2r.exitstatus != 0

    assert shell("find /etc/os-release").returncode == 0


@pytest.mark.test_backup_os_release_with_envar
def test_backup_os_release_with_envar(
    shell,
    convert2rhel,
    custom_subman,
    satellite_registration,
    remove_repositories,
):
    """
    In this scenario the variable `CONVERT2RHEL_INCOMPLETE_ROLLBACK` is set.
    This test case removes all the repos on the system and validates that
    the /etc/os-release package is being backed up and restored during rollback.
    Ref ticket: OAMG-5457. Note that after the test, the $releasever
    variable is unset.
    """

    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        ),
        unregister=True,
    ) as c2r:
        c2r.expect("'CONVERT2RHEL_INCOMPLETE_ROLLBACK' environment variable detected, continuing conversion.")
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0
    assert shell("find /etc/os-release").returncode == 0
