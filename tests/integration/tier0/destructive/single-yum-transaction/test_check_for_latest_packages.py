import re

import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


@pytest.mark.test_packages_upgraded_after_conversion
def test_packages_upgraded_after_conversion(convert2rhel, shell):
    """
    Verify that packages get correctly reinstalled and not
    downgraded during the conversion.
    """

    checked_packages = ["shim-x64"]

    if "oracle-7" in SYSTEM_RELEASE_ENV:
        checked_packages = [
            "krb5-libs.x86_64",
            "nss-softokn-freebl.x86_64",
            "nss-softokn.x86_64",
            "expat.x86_64",
            "krb5-libs.x86_64",
        ]

    packages_to_verify = {}

    for package in checked_packages:
        latest_version = shell(f"repoquery --quiet --latest-limit=1 {package}").output.strip("\n")
        is_installed = shell(f"rpm -q {package}").returncode
        if is_installed == 1:
            shell(f"yum install -y {package}")
        # although not really used, keep the assembled dictionary if needed for version comparison
        # also the dictionary gets appended only when there is the package available to install
        # (repoquery yields a value)
        if latest_version:
            packages_to_verify[package] = latest_version

    # Run utility until the reboot
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0

    package = ""
    options = " --quiet"

    # We need to point the releasever to 8.5 with CentOS latest
    # otherwise the yum check-update looks at releasever 8
    # discovering package versions not available for 8.5
    # Doing that, we also need to disable the epel-modular repo
    # as it raises an 404 error
    if "centos-8-latest" in SYSTEM_RELEASE_ENV:
        options = "--releasever=8.5 --disablerepo epel-modular"

    # Similarly we need to specify releasever for whatever is older than latest,
    # due to the releasever not having the minor reflected.
    match = re.search(r"((\d+)\.(\d+))", SYSTEM_RELEASE_ENV)
    if match:
        options = f"--releasever={match.group()}"
    for package in packages_to_verify:
        # If the package lands on latest version after conversion
        # `yum check-update` will return 0
        # If it is possible to update the package, the yum returncode yields 100
        assert shell(f"yum check-update {package} {options}").returncode == 0
