import os

import pytest

from envparse import env


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
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0

    # Verify, the excluded packages were really removed
    assert shell(f"rpm -qi {packages}").returncode != 0
