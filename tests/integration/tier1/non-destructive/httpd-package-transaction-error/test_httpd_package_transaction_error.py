import pytest

from conftest import TEST_VARS


@pytest.fixture(scope="function")
def handle_packages(shell):
    """
    Handle the installation and removal of the packages required for the test.
    Ensure that system stays in the same state before and after the test.
    """
    # Packages that need to be installed on the system before running the analysis.
    package_to_be_present_before = "httpd"

    # Packages that need to be removed from the system before running the analysis.
    packages_to_be_missing_before = [
        "plymouth",
        "plymouth-core-libs",
        "plymouth-scripts",
    ]

    # Packages that needs to be installed back on the system after the analysis
    # to ensure that the system stays in the same state as before.
    packages_to_be_reinstalled_after = []

    # Packages that needs to be removed from the system after the analysis
    # to ensure that the system stays in the same state as before.
    package_to_be_removed_after = None

    # Install packages
    if shell(f"rpm -q {package_to_be_present_before}").returncode == 1:
        assert shell(f"yum install -y {package_to_be_present_before}").returncode == 0
        package_to_be_removed_after = package_to_be_present_before

    # Remove packages
    for pkg in packages_to_be_missing_before:
        if shell(f"rpm -q {pkg}").returncode == 0:
            packages_to_be_reinstalled_after.append(pkg)
        assert shell(f"yum remove -y {pkg}").returncode == 0

    # Return back to the test
    yield

    if package_to_be_removed_after:
        assert shell(f"yum remove -y {package_to_be_removed_after}").returncode == 0

    for pkg in packages_to_be_reinstalled_after:
        assert shell(f"yum install -y {pkg}").returncode == 0


def test_httpd_package_transaction_error(shell, convert2rhel, handle_packages):
    """
    This test verifies the https://issues.redhat.com/browse/RHELC-1130.
    The yum transaction error happened when some packages depends on each
    other. When a package had dependency on some excluded package (like centos-logos)
    which was removed during the conversion then the package had missing dependency.
    If reinstall of some package happens that brings those dependencies into the transaction
    the error was raised. The problem was mostly caused by the httpd package installed on the
    system.
    """
    # run c2r analyze to verify the yum transaction
    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        index = c2r.expect_exact(
            [
                "Package centos-logos will be swapped to redhat-logos during conversion",
                "Error (Must fix before conversion)",
            ],
            timeout=900,
        )
        assert index == 0, "The analysis found an error. Probably related to the transaction check."
        assert c2r.expect_exact("VALIDATE_PACKAGE_MANAGER_TRANSACTION has succeeded") == 0

    assert c2r.exitstatus == 2
