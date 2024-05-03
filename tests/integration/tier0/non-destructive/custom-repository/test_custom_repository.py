import pytest

from conftest import SystemInformationRelease


class AssignRepositoryVariables:
    """
    Helper class.
    Assign correct repofile content, name and enable_repo_opt to their respective major/eus system version.
    """

    repofile_epel7 = "rhel7"
    repofile_epel8 = "rhel8"
    repofile_epel8_eus = "rhel8-eus"
    enable_repo_opt_epel7 = (
        "--enablerepo rhel-7-server-rpms --enablerepo rhel-7-server-optional-rpms "
        "--enablerepo rhel-7-server-extras-rpms"
    )
    enable_repo_opt_epel8 = "--enablerepo rhel-8-for-x86_64-baseos-rpms --enablerepo rhel-8-for-x86_64-appstream-rpms"
    enable_repo_opt_epel8_eus = (
        "--enablerepo rhel-8-for-x86_64-baseos-eus-rpms --enablerepo rhel-8-for-x86_64-appstream-eus-rpms"
    )

    system_version = SystemInformationRelease.version

    if system_version.major == 7:
        repofile = repofile_epel7
        enable_repo_opt = enable_repo_opt_epel7
    elif system_version.major == 8:
        if system_version.minor == 8:
            repofile = repofile_epel8_eus
            enable_repo_opt = enable_repo_opt_epel8_eus
        else:
            repofile = repofile_epel8
            enable_repo_opt = enable_repo_opt_epel8


@pytest.fixture(scope="function")
def custom_repository(shell):
    """
    Fixture.
    Set up custom repositories.
    Tear down after the test.
    """
    assert shell(f"cp files/{AssignRepositoryVariables.repofile}.repo /etc/yum.repos.d/")

    yield

    assert shell(f"rm -f /etc/yum.repos.d/{AssignRepositoryVariables.repofile}.repo").returncode == 0


@pytest.mark.test_custom_valid_repo_provided
def test_good_conversion_without_rhsm(shell, convert2rhel, custom_repository):
    """
    Verify that --enablerepo is not skipped when subscription-manager is disabled.
    Verify that the passed repositories are accessible.
    """
    with convert2rhel(
        "-y --no-rhsm {} --debug".format(AssignRepositoryVariables.enable_repo_opt), unregister=True
    ) as c2r:
        c2r.expect("The repositories passed through the --enablerepo option are all accessible.")
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1


@pytest.mark.test_custom_invalid_repo_provided
def test_bad_conversion_without_rhsm(shell, convert2rhel, custom_repository):
    """
    Verify that --enablerepo is not skipped when subscription-manager is disabled.
    Verify the conversion will raise CUSTOM_REPOSITORIES_ARE_VALID.UNABLE_TO_ACCESS_REPOSITORIES
    with invalid repository passed.
    Make sure that after failed repo check there is a kernel installed.
    """
    with convert2rhel("-y --no-rhsm --enablerepo fake-rhel-8-for-x86_64-baseos-rpms --debug", unregister=True) as c2r:
        c2r.expect("CUSTOM_REPOSITORIES_ARE_VALID::UNABLE_TO_ACCESS_REPOSITORIES")

    assert c2r.exitstatus == 2

    assert shell("rpm -qi kernel").returncode == 0
