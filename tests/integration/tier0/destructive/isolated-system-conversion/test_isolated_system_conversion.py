import pytest

from conftest import TEST_VARS


@pytest.mark.test_isolated_system_conversion
def test_isolated_system_conversion(convert2rhel):
    """Test converting systems not connected to the Internet but requiring sub-mgr (e.g. managed by Satellite)."""

    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
