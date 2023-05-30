import pytest

from envparse import env


@pytest.mark.rhsm_conversion
def test_run_conversion(convert2rhel):
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
