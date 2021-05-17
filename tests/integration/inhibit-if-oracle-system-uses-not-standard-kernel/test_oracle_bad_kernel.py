import pytest


try:
    from pathlib import Path
except ImportError:
    from pathlib2 import Path

from envparse import env


@pytest.mark.good_tests
def test_good_conversion(convert2rhel):
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Kernel is compatible with RHEL")
    assert c2r.exitstatus == 0


@pytest.mark.bad_tests
def test_bad_conversion(convert2rhel):
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("The booted kernel version is incompatible")
    assert c2r.exitstatus == 1
