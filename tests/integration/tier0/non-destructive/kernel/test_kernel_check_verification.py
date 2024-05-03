import os

import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


@pytest.fixture(scope="function")
def tainted_repository(shell):
    """
    Fixture
    Add a tainted repository with intentionally bad baseurl so the repoquery fails successfully.
    """
    repofile = "broken_repo"
    centos_custom_reposdir = "/usr/share/convert2rhel/repos"

    # For CentOS, we are working with hardcoded repos in /usr/share/convert2rhel/repos/centos-8.5
    if "centos-8" in SYSTEM_RELEASE_ENV:
        shell(f"cp -r files/{repofile}.repo {centos_custom_reposdir}/centos-8.5/")
    shell(f"cp -r files/{repofile}.repo /etc/yum.repos.d/")

    yield

    # Cleanup the tainted repository.
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell(f"rm -f {centos_custom_reposdir}/centos-8.5/{repofile}.repo").returncode == 0
    assert shell(f"rm -f /etc/yum.repos.d/{repofile}.repo").returncode == 0


@pytest.mark.test_failed_repoquery
def test_verify_latest_kernel_check_passes_with_failed_repoquery(convert2rhel, tainted_repository):
    """
    This test verifies, that failed repoquery is handled correctly.
    Failed repoquery subsequently caused the latest kernel check to fail.
    Introduced fixes should get the process past the latest kernel check.
    """
    # Run the conversion just past the latest kernel check, if successful, end the conversion there.
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect(
            "Couldn't fetch the list of the most recent kernels available in the repositories. Did not perform the loaded kernel check.",
            timeout=300,
        )
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1


@pytest.mark.parametrize("yum_conf_exclude", [["kernel", "kernel-core"]], indirect=True)
@pytest.mark.test_yum_exclude_kernel
def test_latest_kernel_check_with_exclude_kernel_option(convert2rhel, yum_conf_exclude):
    """
    Verify, the conversion does not raise:
    'Could not find any kernel from repositories to compare against the loaded kernel.'
    When `exclude=kernel kernel-core` is defined in yum.conf
    Verify IS_LOADED_KERNEL_LATEST has succeeded is raised and terminate the utility.
    """
    # Run the conversion and verify that it proceeds past the latest kernel check
    # if so, interrupt the conversion
    with convert2rhel("-y --debug") as c2r:
        if c2r.expect("IS_LOADED_KERNEL_LATEST has succeeded") == 0:
            c2r.sendcontrol("c")
        else:
            assert AssertionError, "Utility did not raise IS_LOADED_KERNEL_LATEST has succeeded"

    assert c2r.exitstatus == 1


@pytest.mark.test_non_latest_kernel_error
def test_non_latest_kernel_error(kernel, shell, convert2rhel):
    """
    System has non latest kernel installed.
    Verify the IS_LOADED_KERNEL_LATEST.INVALID_KERNEL_VERSION is raised.
    """
    if os.environ["TMT_REBOOT_COUNT"] == "1":
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                TEST_VARS["RHSM_SERVER_URL"],
                TEST_VARS["RHSM_USERNAME"],
                TEST_VARS["RHSM_PASSWORD"],
                TEST_VARS["RHSM_POOL"],
            )
        ) as c2r:
            c2r.expect("Check if the loaded kernel version is the most recent")
            c2r.expect_exact("(OVERRIDABLE) IS_LOADED_KERNEL_LATEST:INVALID_KERNEL_VERSION")
            c2r.sendcontrol("c")

        assert c2r.exitstatus == 1
