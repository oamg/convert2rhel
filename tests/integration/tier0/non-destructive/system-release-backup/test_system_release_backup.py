import os

import pytest

from conftest import TEST_VARS


@pytest.fixture(scope="function")
def system_release_missing(shell, backup_directory):
    """
    Fixture.
    Back up and remove the /etc/system-release file.
    Restore in the teardown phase.
    """
    system_release_bak = os.path.join(backup_directory, "system-release")
    system_release = "/etc/system-release"
    # Make backup copy of the file
    assert shell(f"mv -v {system_release} {system_release_bak}").returncode == 0

    yield

    # Restore the system
    assert shell(f"mv -v {system_release_bak} {system_release}").returncode == 0


def test_inhibitor_missing_system_release(shell, convert2rhel, system_release_missing):
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

    assert c2r.exitstatus == 1


@pytest.mark.parametrize("fixture_satellite", ["RHEL_CONTENT_SAT_REG"], indirect=True)
def test_inhibitor_os_release_restored(shell, convert2rhel, fixture_satellite, remove_repositories):
    """
    We remove all the system repositories from the usual location.
    Since the host is registered through Satellite having access only to the RHEL repositories,
    convert2rhel is unable to perform back-up of some packages.
    In this scenario the variable `CONVERT2RHEL_INCOMPLETE_ROLLBACK` is not set, therefore
    using analyze we expect convert2rhel to raise an error and return code 1.
    The test validates, that the /etc/os-release file got correctly backed-up and restored
    during the utility run.
    """
    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel("--debug", unregister=True) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect_exact("set the environment variable 'CONVERT2RHEL_INCOMPLETE_ROLLBACK", timeout=600)
    # We expect the return code to be 2, given an error is raised
    assert c2r.exitstatus == 2

    assert shell("find /etc/os-release").returncode == 0


@pytest.mark.parametrize("fixture_satellite", ["RHEL_CONTENT_SAT_REG"], indirect=True)
def test_override_inhibitor_os_release_restored(
    shell,
    convert2rhel,
    fixture_satellite,
    remove_repositories,
):
    """
    We remove all the system repositories from the usual location.
    Since the host is registered through Satellite having access only to the RHEL repositories,
    convert2rhel is unable to perform back-up of some packages.
    In this scenario the variable `CONVERT2RHEL_INCOMPLETE_ROLLBACK` is set.
    The test validates, that the /etc/os-release file got correctly backed-up and restored
    during the utility run.
    Ref ticket: OAMG-5457.
    Note that after the test, the $releasever variable is unset.
    That is due to the incomplete rollback not being able to back up/restore the *-linux-release
    package, the issue gets resolved by the (autoused) `workaround_missing_os_release_package` fixture.
    """
    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("'CONVERT2RHEL_INCOMPLETE_ROLLBACK' environment variable detected, continuing conversion.")

        # Apparently the whole "/etc/yum.repos.d" dir is missing when the *-release package gets erased
        # re-create it, so sub-man is able to refresh the redhat.repo file
        # TODO remove this part when/if https://issues.redhat.com/browse/RHELC-1677 gets fixed
        c2r.expect("Ensure kernel modules compatibility with RHEL")
        missing_dir = "/etc/yum.repos.d"
        if not os.path.exists(missing_dir):
            os.mkdir(missing_dir)

        c2r.expect("Continue with the system conversion")
        c2r.sendline("n")
    assert c2r.exitstatus == 1

    assert shell("find /etc/os-release").returncode == 0
