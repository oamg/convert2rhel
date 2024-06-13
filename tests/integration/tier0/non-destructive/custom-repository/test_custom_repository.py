import pytest

from conftest import SYSTEM_RELEASE_ENV, SystemInformationRelease


class AssignRepositoryVariables:
    """
    Helper class.
    Assign correct repofile content, name and enable_repo_opt to their respective major/eus system version.
    """

    system_version = SystemInformationRelease.version.major

    repofile_el7 = "rhel7"
    enable_repo_opt_el7 = (
        "--enablerepo rhel-7-server-rpms --enablerepo rhel-7-server-optional-rpms "
        "--enablerepo rhel-7-server-extras-rpms"
    )
    repofile_el = f"rhel{system_version}"
    enable_repo_opt_el = f"--enablerepo rhel-{system_version}-for-x86_64-baseos-rpms --enablerepo rhel-{system_version}-for-x86_64-appstream-rpms"
    repofile_el_eus = f"rhel{system_version}-eus"
    enable_repo_opt_el_eus = f"--enablerepo rhel-{system_version}-for-x86_64-baseos-eus-rpms --enablerepo rhel-{system_version}-for-x86_64-appstream-eus-rpms"

    if system_version == 7:
        repofile = repofile_el7
        enable_repo_opt = enable_repo_opt_el7
    elif system_version >= 8:
        # We want to assign EUS repositories to EUS eligible minor releases,
        # but only in the case when the release is not currently the latest
        # (denoted by "-latest" in the test metadata)
        if SystemInformationRelease.version.minor in (2, 4, 6, 8) and "latest" not in SYSTEM_RELEASE_ENV:
            repofile = repofile_el_eus
            enable_repo_opt = enable_repo_opt_el_eus
        else:
            repofile = repofile_el
            enable_repo_opt = enable_repo_opt_el


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


def test_custom_valid_repo_without_rhsm(shell, convert2rhel, custom_repository):
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


def test_custom_invalid_repo_without_rhsm(shell, convert2rhel, custom_repository):
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
