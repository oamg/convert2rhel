import platform


def test_install_problematic_package(shell):
    """Need to install a package, which is in CentOS repos (which we are converting) and is not present in RHEL
    repositories. The package in question (cpaste) is from the CentOS Extras repo which is enabled by default on
    CentOS systems.

    When the test starts failing we will need to change the selected package."""

    # On artemis images exists packages that needs to be removed so `yum distro-sync` will fail on cpaste.
    # Otherwise it would not fail (yum return 0 when at least one package is ok)
    if "centos-8" in platform.platform():
        assert (
            shell("yum remove python2-pip python2-pip-wheel python2-setuptools python2-setuptools-wheel -y").returncode
            == 0
        )
    assert shell("yum install -y cpaste").returncode == 0
