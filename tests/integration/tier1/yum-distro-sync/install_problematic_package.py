from conftest import SYSTEM_RELEASE_ENV


def test_install_problematic_package(shell):
    """
    Install a package, which is in CentOS repos and is not present in RHEL repositories.
    The package in question (cpaste) is from the CentOS Extras repo which is enabled by default on
    CentOS systems.

    When the test starts failing we will need to change the selected package.
    """

    # There are packages some packages on the artemis CentOS-8 guest, that need to be removed
    # so `yum distro-sync` will fail on cpaste.
    # If not removed, the `yum distro-sync` would not fail (yum return 0 when at least one package is ok)
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert (
            shell("yum remove python2-pip python2-pip-wheel python2-setuptools python2-setuptools-wheel -y").returncode
            == 0
        )
    assert shell("yum install -y cpaste").returncode == 0
