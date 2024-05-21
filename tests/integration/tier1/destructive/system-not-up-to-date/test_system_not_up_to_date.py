import os

import pytest

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


@pytest.fixture()
def downgrade_and_versionlock(shell):
    """
    Fixture to install, downgrade and versionlock some packages.
    This simulates
    1. System packages not updated
    2. Version lock in use
    We install the packages from old version's repositories to make sure
    the package won't be on it's latest version in case it cannot be
    downgraded.
    """
    # On some systems we cannot do the downgrade as the repos contain only the latest package version.
    # We need to install package from older repository as a workaround.
    centos_8_pkg_url = "https://vault.centos.org/8.1.1911/BaseOS/x86_64/os/Packages/wpa_supplicant-2.7-1.el8.x86_64.rpm"
    alma_8eus_pkg_url = (
        "https://repo.almalinux.org/vault/8.3/BaseOS/x86_64/os/Packages/wpa_supplicant-2.9-2.el8_3.1.x86_64.rpm"
    )
    rocky_8eus_pkg_url = (
        "https://dl.rockylinux.org/vault/rocky/8.3/BaseOS/x86_64/os/Packages/wpa_supplicant-2.9-2.el8.1.x86_64.rpm"
    )

    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install -y {}".format(centos_8_pkg_url)).returncode == 0
    elif "alma-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install -y {}".format(alma_8eus_pkg_url)).returncode == 0
    elif "rocky-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install -y {}".format(rocky_8eus_pkg_url)).returncode == 0
    else:
        assert shell("yum install openldap wpa_supplicant sqlite -y").returncode == 0
        # Try to downgrade some packages.
        assert shell("yum downgrade openldap wpa_supplicant sqlite -y").returncode == 0

    assert shell("yum install -y yum-plugin-versionlock").returncode == 0
    assert shell("yum versionlock wpa_supplicant sqlite").returncode == 0


@pytest.mark.test_system_not_updated
def test_system_not_updated(shell, convert2rhel, downgrade_and_versionlock):
    """
    System contains at least one package that is not updated to
    the latest version. The c2r has to display a warning message
    about that. Also, not updated package has its version locked.
    Display a warning about used version lock.
    Since the introduction of overridables, we need to use
    CONVERT2RHEL_OUTDATED_PACKAGE_CHECK_SKIP to override out of date
    packages.
    """
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("WARNING - YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        c2r.expect(r"WARNING - The system has \d+ package\(s\) not updated")
        c2r.expect_exact("ERROR - (OVERRIDABLE) PACKAGE_UPDATES::OUT_OF_DATE_PACKAGES - Outdated packages detected")
    assert c2r.exitstatus == 2

    # We need to set envar to override the out of date packages check
    # to perform the full conversion
    os.environ["CONVERT2RHEL_OUTDATED_PACKAGE_CHECK_SKIP"] = "1"

    # Run utility until the reboot
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        c2r.expect("WARNING - YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        c2r.expect_exact("Detected 'CONVERT2RHEL_OUTDATED_PACKAGE_CHECK_SKIP' environment variable")
        c2r.expect(r"WARNING - The system has \d+ package\(s\) not updated")
    assert c2r.exitstatus == 0
