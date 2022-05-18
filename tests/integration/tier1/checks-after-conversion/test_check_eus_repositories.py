import platform


def test_enabled_eus_repositories(shell):
    """Testing, if the EUS repostitories are enabled after conversion"""
    if platform.platform() == "RHEL-8.4":
        shell("yum repolist")
    else:
        pass
