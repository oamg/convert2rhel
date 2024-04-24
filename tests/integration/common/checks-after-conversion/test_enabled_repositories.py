import os.path
import re

import pytest

from conftest import SystemInformationRelease


def _check_enabled_repos_rhel8(enabled_repos: str = "", eus: bool = False):
    """Helper function to assert RHEL repositories."""
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


@pytest.mark.test_enabled_repositories
def test_enabled_repositories(shell):
    """
    Verify that the correct repositories (including EUS if applies) are enabled after the conversion.
    """

    try:
        enabled_repos = shell("yum repolist").output
        system_release = SystemInformationRelease()
        assert "redhat" in system_release.distribution

        if system_release.version.major == 7 and system_release.version.minor == 9:
            assert "rhel-7-server-rpms/7Server/x86_64" in enabled_repos
        elif system_release.version.major == 8:
            # Handle the special test case scenario where we do not use the
            # premium account with EUS repositories
            if os.path.exists("/eus_repos_used"):
                _check_enabled_repos_rhel8(enabled_repos, eus=True)
            else:
                _check_enabled_repos_rhel8(enabled_repos)
    finally:
        # We need to unregister the system after the conversion
        shell("subscription-manager unregister")
