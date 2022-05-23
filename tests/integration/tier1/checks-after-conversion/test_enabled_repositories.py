import platform


def test_enabled_repositories(shell):
    """Testing, if the EUS repostitories are enabled after conversion"""
    system_version = platform.platform()
    enabled_repos = shell("yum repolist").output

    # Once we will decide to use EUS 8.6 we have to add them here as well
    if "redhat-8.4" in system_version:
        assert "rhel-8-for-x86_64-appstream-eus-rpms" in enabled_repos
        assert "rhel-8-for-x86_64-baseos-eus-rpms" in enabled_repos
    elif "redhat-8.5" in system_version or "redhat-8.6" in system_version:
        assert "rhel-8-for-x86_64-baseos-rpms" in enabled_repos
        assert "rhel-8-for-x86_64-appstream-rpms" in enabled_repos
    elif "redhat-7.9" in system_version:
        assert "rhel-7-server-rpms/7Server/x86_64" in enabled_repos

    # We need to unregister the system after the conversion
    shell("subscription-manager unregister")
