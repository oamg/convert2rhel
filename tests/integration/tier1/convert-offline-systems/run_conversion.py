import os
import platform

from envparse import env


def test_convert_offline_systems(shell, convert2rhel):
    """Test converting systems not connected to the Internet but requiring sub-mgr (e.g. managed by Satellite)."""

    # The CentOS8 Extras repo url is unreachable due to offline system setup.
    # The repoquery returns an error, thus we need to disable this repository.
    if "centos-8" in platform.platform():
        shell("yum-config-manager --disable extras --disable epel-modular --disable appstream")

    os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"] = "1"
    with convert2rhel(
        ("-y --no-rpm-va -k {} -o {} --keep-rhsm --debug").format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
