import pytest

from conftest import TEST_VARS


@pytest.mark.test_satellite_conversion
def test_satellite_conversion(shell, convert2rhel, satellite_registration):
    """
    Conversion method using the Satellite credentials for registration.
    The subscription-manager package is removed for this conversion method.
    Use the provided curl command to download the registration script to a file,
    then run the registration script file.
    """
    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
