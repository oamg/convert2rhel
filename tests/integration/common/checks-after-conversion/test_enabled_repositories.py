import os.path
import re

import pytest

from conftest import SystemInformationRelease


def _check_enabled_repos_rhel8(enabled_repos: str = "", eus: bool = False):
    """Helper function to assert correct RHEL8 repositories are enabled after the conversion."""
    baseos_repo = ""
    appstream_repo = ""
    if eus:
        baseos_repo = "rhel-8-for-x86_64-baseos-eus-rpms"
        appstream_repo = "rhel-8-for-x86_64-appstream-eus-rpms"
    else:
        baseos_repo = "rhel-8-for-x86_64-baseos-rpms"
        appstream_repo = "rhel-8-for-x86_64-appstream-rpms"

    assert baseos_repo in enabled_repos
    assert appstream_repo in enabled_repos


def _check_enabled_repos_rhel7(enabled_repos: str = "", els: bool = False):
    """Helper function to assert correct RHEL7 repositories are enabled after the conversion."""
    repo = ""
    if els:
        repo = "rhel-7-server-els-rpms"
    else:
        repo = "rhel-7-server-rpms"

    assert repo in enabled_repos


@pytest.mark.test_enabled_repositories
def test_enabled_repositories(shell):
    """
    Verify that the correct repositories (including EUS/ELS if applies) are enabled after the conversion.
    """

    try:
        enabled_repos = shell("yum repolist").output
        system_release = SystemInformationRelease()
        assert "redhat" in system_release.distribution

        if system_release.version.major == 7:
            # Handle the special test case scenario where we use the
            # account with the ELS repositories available
            is_els = os.path.exists("/els_repos_used")
            _check_enabled_repos_rhel7(enabled_repos, els=is_els)
        elif system_release.version.major == 8:
            # Handle the special test case scenario where we use the
            # account with the EUS repositories available
            is_eus = os.path.exists("/eus_repos_used")
            _check_enabled_repos_rhel8(enabled_repos, eus=is_eus)
    finally:
        # We need to unregister the system after the conversion
        shell("subscription-manager unregister")
