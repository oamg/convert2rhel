import pytest

from conftest import SystemInformationRelease, get_custom_repos_names


@pytest.fixture(scope="function")
def set_custom_repository_files(shell):
    """
    Fixture.
    Set up custom repositories.
    Tear down after the test.
    """
    repo_file_name = f"rhel{SystemInformationRelease.version.major}"
    if SystemInformationRelease.is_eus:
        repo_file_name += "-eus"

    assert shell(f"cp files/{repo_file_name}.repo /etc/yum.repos.d/").returncode == 0

    yield

    assert shell(f"rm -f /etc/yum.repos.d/{repo_file_name}.repo").returncode == 0


def test_custom_valid_repo_without_rhsm(convert2rhel, set_custom_repository_files):
    """
    Verify that --enablerepo is not skipped when subscription-manager is disabled.
    Verify that the passed repositories are accessible.
    """
    # Join the --enablerepo <repo> on whitespace
    enable_repo_opt = " ".join(f"--enablerepo {repo}" for repo in get_custom_repos_names())

    with convert2rhel(f"-y --no-rhsm {enable_repo_opt} --debug", unregister=True) as c2r:
        c2r.expect("The repositories passed through the --enablerepo option are all accessible.")
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1


def test_custom_invalid_repo_without_rhsm(shell, convert2rhel):
    """
    Verify that --enablerepo is not skipped when subscription-manager is disabled.
    Verify the conversion will raise CUSTOM_REPOSITORIES_ARE_VALID.UNABLE_TO_ACCESS_REPOSITORIES
    with invalid repository passed.
    Make sure that after failed repo check there is a kernel installed.
    """
    with convert2rhel("-y --no-rhsm --enablerepo fake-rhel-8-for-x86_64-baseos-rpms --debug", unregister=True) as c2r:
        c2r.expect("CUSTOM_REPOSITORIES_ARE_VALID::UNABLE_TO_ACCESS_REPOSITORIES")

    assert c2r.exitstatus == 2

    assert shell("rpm -q kernel").returncode == 0
