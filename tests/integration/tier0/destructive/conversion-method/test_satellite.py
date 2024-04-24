import pytest

from conftest import TEST_VARS, satellite_registration_command


@pytest.mark.test_satellite_conversion
def test_satellite_conversion(shell, convert2rhel):
    """
    Conversion method using the Satellite credentials for registration.
    The subscription-manager package is removed for this conversion method.
    Subscribe to the Satellite server using the curl command.
    """

    sat_reg_command = satellite_registration_command()

    assert shell(sat_reg_command).returncode == 0

    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
