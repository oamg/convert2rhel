import os

from conftest import SATELLITE_PKG_DST, SATELLITE_PKG_URL, SYSTEM_RELEASE_ENV
from envparse import env


def test_backup_os_release_no_envar(shell, convert2rhel):
    """
    In this scenario there is no variable `CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK` set.
    This means the conversion is inhibited in early stage.
    This test case removes all the repos on the system which prevents the backup of some files.
    Satellite is being used in all of test cases.
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

    # Move all repos to other location, so it is not being used
    assert shell("mkdir /tmp/s_backup").returncode == 0
    assert shell("mv /etc/yum.repos.d/* /tmp/s_backup/").returncode == 0

    # EUS version use hardcoded repos from c2r as well
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell("mkdir /tmp/s_backup_eus").returncode == 0
        assert shell("mv /usr/share/convert2rhel/repos/* /tmp/s_backup_eus/").returncode == 0

    # Since we are moving all repos away, we need to bypass kernel check
    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"

    assert shell("find /etc/os-release").returncode == 0
    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug --keep-rhsm".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        c2r.expect("set the environment variable 'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK.")
        assert c2r.exitstatus != 0

    assert shell("find /etc/os-release").returncode == 0


def test_backup_os_release_with_envar(shell, convert2rhel):
    """
    In this scenario the variable `CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK` is set.
    This test case removes all the repos on the system and validates that
    the /etc/os-release package is being backed up and restored during rollback.
    Ref ticket: OAMG-5457. Note that after the test, the $releaserver
    variable is unset.
    """

    assert shell("find /etc/os-release").returncode == 0

    os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"] = "1"

    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug --keep-rhsm".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        ),
    ) as c2r:
        c2r.expect(
            "'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK' environment variable detected, continuing conversion."
        )
        c2r.send(chr(3))
        c2r.sendcontrol("d")

    assert shell("find /etc/os-release").returncode == 0

    # Return repositories to their original location
    assert shell("mv /tmp/s_backup/* /etc/yum.repos.d/").returncode == 0

    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell("mv /tmp/s_backup_eus/* /usr/share/convert2rhel/repos/").returncode == 0

    # Clean up
    del os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"]
    del os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"]


def test_backup_os_release_wrong_registartion(shell, convert2rhel):
    """
    Verify that the os-release file is restored when the satellite registartion fails.
    Refrence issue: RHELC-51
    """
    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel("-y --no-rpm-va -k wrong_key -o rUbBiSh_pWd --debug --keep-rhsm") as c2r:
        c2r.expect("Unable to register the system through subscription-manager.")
        c2r.expect("Restore /etc/os-release from backup")

    assert shell("find /etc/os-release").returncode == 0


def test_missing_system_release(shell, convert2rhel):
    """
    It is required to have /etc/system-release file present on the system.
    If the file is missing inhibit the conversion.
    """

    # Make backup copy of the file
    assert shell("mv /etc/system-release /tmp/s_backup/").returncode == 0

    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        c2r.expect("Unable to find the /etc/system-release file containing the OS name and version")

    assert c2r.exitstatus != 0

    # Restore the system
    assert shell("mv /tmp/s_backup/system-release /etc/").returncode == 0
