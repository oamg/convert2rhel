import os

from envparse import env


def test_remove_excluded_pkgs(shell, convert2rhel):
    """
    Ensure Convert2RHEL removes packages, which are specified as excluded_pkgs in config.
    Verification scenarios cover just some packages causing major issues.
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
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")

    # check excluded packages were really removed
    assert shell(f"rpm -qi {packages}").returncode != 0
