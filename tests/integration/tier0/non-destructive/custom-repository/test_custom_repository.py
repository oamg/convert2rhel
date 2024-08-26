import pytest

from conftest import SYSTEM_RELEASE_ENV, SystemInformationRelease


def _assign_enable_repo_opt():
    """
    Helper function.
    Assign correct repofile content, name and enable_repo_opt to their respective major/eus system version.
    """
    system_version = SystemInformationRelease.version
    system_distribution = SystemInformationRelease.distribution
    repos = ("rhel-7-server-rpms", "rhel-7-server-optional-rpms", "rhel-7-server-extras-rpms")
    enable_opt = "--enablerepo"
    repofile = f"rhel{system_version.major}"

    if system_version.major in (8, 9):
        # We want to go for EUS repositories only where really applicable
        #   1/ minor version matches EUS eligible version
        #   2/ the system distribution does snapshots of said versions
        #   3/ the current version is not the latest one available (i.e. not in the EUS phase yet)
        if system_version.minor in (4, 6, 8) and system_distribution != "oracle" and "latest" not in SYSTEM_RELEASE_ENV:
            repos = (
                f"rhel-{system_version.major}-for-x86_64-baseos-eus-rpms",
                f"rhel-{system_version.major}-for-x86_64-appstream-eus-rpms",
            )
            # Append '-eus' to the name of the repofile
            repofile += "-eus"
        else:
            repos = (
                f"rhel-{system_version.major}-for-x86_64-baseos-rpms",
                f"rhel-{system_version.major}-for-x86_64-appstream-rpms",
            )

    # Join the --enablerepo <repo> on whitespace
    enable_repo_opt = " ".join(f"{enable_opt} {repo}" for repo in repos)

    return repofile, enable_repo_opt


REPOFILE, ENABLE_REPO_OPT = _assign_enable_repo_opt()


@pytest.fixture(scope="function")
def custom_repository(shell):
    """
    Fixture.
    Set up custom repositories.
    Tear down after the test.
    """
    assert shell(f"cp files/{REPOFILE}.repo /etc/yum.repos.d/")

    yield

    assert shell(f"rm -f /etc/yum.repos.d/{REPOFILE}.repo").returncode == 0


def test_custom_valid_repo_without_rhsm(shell, convert2rhel, custom_repository):
    """
    Verify that --enablerepo is not skipped when subscription-manager is disabled.
    Verify that the passed repositories are accessible.
    """
    with convert2rhel("-y --no-rhsm {} --debug".format(ENABLE_REPO_OPT), unregister=True) as c2r:
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

    assert shell("rpm -q kernel").returncode == 0
