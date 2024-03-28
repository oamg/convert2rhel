import os

import pytest

from conftest import TEST_VARS


@pytest.mark.test_excluded_packages_removed
def test_excluded_packages_removed(shell, convert2rhel):
    """
    Verify, that convert2rhel removes packages, which are specified as excluded_pkgs in config.
    Verification scenarios cover just some of the packages causing the most issues.
    Those are specified in their respective test plan (remove_excluded_pkgs_epel7 and remove_excluded_pkgs_epel8).
    Packages are set as an environment variable.
    """
    packages = os.environ["PACKAGES"]
    assert (
        shell(
            f"yum install -y {packages}",
        ).returncode
        == 0
    )

    # run utility until the reboot
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0

    # Verify, the excluded packages were really removed
    assert shell(f"rpm -qi {packages}").returncode != 0
