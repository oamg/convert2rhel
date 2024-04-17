import pytest

from conftest import TEST_VARS


@pytest.mark.test_activation_key_conversion
def test_activation_key_conversion(convert2rhel):
    """
    Basic conversion method using the RHSM activation key and organization for registration.
    """
    with convert2rhel(
        "-y --serverurl {} -k {} -o {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_KEY"],
            TEST_VARS["RHSM_ORG"],
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
