import re

from collections import namedtuple

import pytest


# TODO(danmyway) move to conftest
class GetSystemInformation:
    """
    Helper class.
    Assign a namedtuple with major and minor elements, both of an int type.
    Assign a distribution (e.g. centos, oracle, rocky, alma)
    Assign a system release.

    Examples:
    Oracle Linux Server release 7.8
    CentOS Linux release 7.6.1810 (Core)
    CentOS Linux release 8.1.1911 (Core)
    """

    with open("/etc/system-release", "r") as file:
        system_release_content = file.read()
        match_version = re.search(r".+?(\d+)\.(\d+)\D?", system_release_content)
        if not match_version:
            print("not match")
        version = namedtuple("Version", ["major", "minor"])(int(match_version.group(1)), int(match_version.group(2)))
        distribution = system_release_content.split()[0].lower()
        system_release = "{}-{}.{}".format(distribution, version.major, version.minor)


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

    with open("/etc/system-release", "r") as file:
        system_release = file.read()
        system_version = GetSystemInformation.version

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

    assert c2r.exitstatus != 0


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

    assert c2r.exitstatus != 0

    assert shell("rpm -qi kernel").returncode == 0
