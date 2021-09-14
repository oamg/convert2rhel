def test_install_problematic_package(shell):
    """Need to install a package, which is in CentOS repos (which we are converting) and is not present in RHEL
    repositories. The package in question (cpaste) is from the CentOS Extras repo which is enabled by default on
    CentOS systems.

    When the test starts failing we will need to change the selected package."""

    assert shell("yum install -y cpaste").returncode == 0
