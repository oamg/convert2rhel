import pytest

from conftest import TEST_VARS


@pytest.fixture
def problematic_third_party_package(shell):
    """
    Install problematic package which previously caused the TASK - [Prepare: List third-party packages]
    to fail.
    Installed package(s):
    v8-devel from the epel repository
    nodejs from the epel repository
    """
    problematic_pkg_and_repo = {"v8-devel": "epel", "nodejs": "epel"}
    package_installed = []

    for pkg, repo in problematic_pkg_and_repo.items():
        if shell(f"rpm -q {pkg}").returncode == 1:
            shell(f"yum install -y {pkg} --enablerepo={repo}")
            package_installed.append(pkg)

    yield

    for pkg in package_installed:
        shell(f"yum remove -y {pkg}")


def test_list_third_party_pkgs(convert2rhel, problematic_third_party_package):
    """
    This test verifies, that the  TASK - [Prepare: List third-party packages]
    won't fail listing packages if previously problematic third party packages are installed.
    Installed package(s):
    v8-devel from the epel repository
    nodejs from the epel repository
    """
    with convert2rhel(
        "analyze -y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        # Verify that the analysis report is printed
        c2r.expect("Pre-conversion analysis report", timeout=600)

    # The analysis should exit with 0, if it finishes successfully
    assert c2r.exitstatus == 0
