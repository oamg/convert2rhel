import os

from envparse import env


def test_convert_offline_systems(convert2rhel):
    """Test converting systems not connected to the Internet but requiring sub-mgr (e.g. managed by Satellite)."""

    os.environ["CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK"] = "1"
    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"

    with convert2rhel(
        ("-y --no-rpm-va -k {} -o {} --keep-rhsm --debug").format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
