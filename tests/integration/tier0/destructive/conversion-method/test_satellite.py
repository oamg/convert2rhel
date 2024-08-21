from conftest import TEST_VARS


def test_satellite_conversion(convert2rhel, fixture_satellite):
    """
    Conversion method using the Satellite credentials for registration.
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
