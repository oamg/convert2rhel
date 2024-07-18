from conftest import SYSTEM_RELEASE_ENV, SystemInformationRelease


def test_install_dependency_packages(shell):
    """
    Having certain packages installed used to cause conversion failures - namely yum dependency resolution errors.

    This test verifies that having these packages pre-installed does not cause a failure anymore
    """

    dependency_pkgs = [
        "abrt-retrace-client",  # OAMG-4447
        "libreport-cli",  # OAMG-4447
        "ghostscript-devel",  # Case 02855547
        "python2-dnf",  # OAMG-4690
        "python2-dnf-plugins-core",  # OAMG-4690
        "redhat-lsb-trialuse",  # OAMG-4942
        "ldb-tools",  # OAMG-4941
        "gcc-c++",  # OAMG-6136
        "python-requests",  # OAMG-4936
    ]
    if SystemInformationRelease.version.major == 8:
        if SystemInformationRelease.distribution == "oracle":
            dependency_pkgs = [
                "iwl7260-firmware",  # RHELC-567
                "iwlax2xx-firmware",  # RHELC-567 - causing problems during the conversion on OL8
            ]
        else:
            dependency_pkgs = [
                "python39-psycopg2-debug",  # OAMG-5239, OAMG-4944 - package not available on Oracle Linux 8
            ]

    # installing dependency packages
    assert shell("yum install -y {}".format(" ".join(dependency_pkgs))).returncode == 0
