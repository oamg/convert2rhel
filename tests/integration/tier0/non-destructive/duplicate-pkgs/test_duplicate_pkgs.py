import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


DUPLICATE_PKG_URL_MAPPING = {
    "centos-7": "https://vault.centos.org/7.4.1708/os/x86_64/Packages/python2-cryptography-1.7.2-1.el7.x86_64.rpm",
    "oracle-7": "https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/abrt-2.1.11-50.0.1.el7.x86_64.rpm",
}

DUPLICATE_PKG_URL = DUPLICATE_PKG_URL_MAPPING[SYSTEM_RELEASE_ENV]


@pytest.fixture(scope="function")
def install_duplicate_pkg(shell):
    """
    Install duplicate package on the system.
    """
    pkg = ""
    pkg_was_installed = True

    if SYSTEM_RELEASE_ENV == "centos-7":
        pkg = "python2-cryptography"
    elif SYSTEM_RELEASE_ENV == "oracle-7":
        pkg = "abrt"

    # Install `pkg` from the latest repository
    if shell(f"rpm -q {pkg}").returncode == 1:
        shell(f"yum install -y {pkg}")
        pkg_was_installed = False

    # Download and install duplicate package with different version
    shell(f"curl -o duplicate-{pkg}.rpm {DUPLICATE_PKG_URL}")
    shell(f"rpm -i --noscripts --justdb --nodeps --force duplicate-{pkg}.rpm")

    assert int(shell(f"rpm -q {pkg} | wc -l ").output) >= 2

    yield

    # This should remove both the packages
    shell(f"yum remove -y {pkg}")

    # If the package was originally installed on the system, install it back
    if pkg_was_installed:
        shell(f"yum install -y {pkg}")


def test_duplicate_packages_installed(convert2rhel, install_duplicate_pkg):
    """
    Verify that the conversion does not crash when the same
    package (of different version) is installed on the system.
    Verify that the proper inhibitor is raised.
    """
    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        # The error about duplicate packages should be included at the end of the pre-conversion analysis report
        c2r.expect("Pre-conversion analysis report", timeout=600)
        c2r.expect_exact("(ERROR) DUPLICATE_PACKAGES::DUPLICATE_PACKAGES_FOUND")

    # The analysis should exit with 2, if inhibitor is found
    assert c2r.exitstatus == 2
