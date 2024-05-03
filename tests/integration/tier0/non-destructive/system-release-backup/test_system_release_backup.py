import pytest

from conftest import SAT_REG_FILE, TEST_VARS


@pytest.fixture(scope="function")
def system_release_missing(shell):
    """
    Fixture.
    Back up and remove the /etc/system-release file.
    Restore in the teardown phase.
    """
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


@pytest.mark.parametrize("rhel_content_key", [SAT_REG_FILE["RHEL_CONTENT_SAT_REG"]])
@pytest.mark.test_backup_os_release_no_envar
def test_backup_os_release_no_envar(shell, convert2rhel, satellite_registration, rhel_content_key, remove_repositories):
    """
    We remove all the system repositories from the usual location.
    Since the host is registered through Satellite having access only to the RHEL repositories,
    convert2rhel is unable to perform back-up of some packages.
    In this scenario the variable `CONVERT2RHEL_INCOMPLETE_ROLLBACK` is not set, therefore
    using analyze we expect convert2rhel to raise an error and return code 1.
    The test validates, that the /etc/os-release file got correctly backed-up and restored
    during the utility run.
    """
    # Register to the Satellite to access only the RHEL repositories
    satellite_registration(rhel_content_key)

    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel(
        "analyze -y --debug",
        unregister=True,
    ) as c2r:
        c2r.expect("set the environment variable 'CONVERT2RHEL_INCOMPLETE_ROLLBACK")
        # We expect the return code to be 1, given an error is raised
        assert c2r.exitstatus == 1

    assert shell("find /etc/os-release").returncode == 0


@pytest.mark.parametrize("rhel_content_key", [SAT_REG_FILE["RHEL_CONTENT_SAT_REG"]])
@pytest.mark.test_backup_os_release_with_envar
def test_backup_os_release_with_envar(
    shell,
    convert2rhel,
    satellite_registration,
    rhel_content_key,
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
    package, the issue gets resolved by the (autoused) missing_os_release_package_workaround fixture.
    """
    # Register to the Satellite to access only the RHEL repositories
    satellite_registration(rhel_content_key)

    assert shell("find /etc/os-release").returncode == 0

    with convert2rhel(
        "analyze -y --debug",
        unregister=True,
    ) as c2r:
        c2r.expect("'CONVERT2RHEL_INCOMPLETE_ROLLBACK' environment variable detected, continuing conversion.")

        # We bypass the error by using the environment variable,
        # the analysis should therefore finish successfully
        assert c2r.exitstatus == 0

    assert shell("find /etc/os-release").returncode == 0
