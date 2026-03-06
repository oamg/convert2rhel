import os

from conftest import TEST_VARS


def test_satellite_conversion(convert2rhel, fixture_satellite, shell):
    """
    Conversion method using the Satellite credentials for registration.
    Use the provided curl command to download the registration script to a file,
    then run the registration script file.
    """
    releasever_envar = os.environ.get("SYSTEM_RELEASE_ENV")
    if "latest" in releasever_envar:
        releasever = releasever_envar.split("-")[1]
        shell(f"subscription-manager release --set {releasever}")
    with convert2rhel(
        "-y -k {} -o {} --debug".format(
            TEST_VARS["SATELLITE_KEY"],
            TEST_VARS["SATELLITE_ORG"],
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
