import pytest

from envparse import env


@pytest.mark.test_activation_key_conversion
def test_activation_key_conversion(convert2rhel):
    """
    Basic conversion method using the RHSM activation key and organization for registration.
    """
    with convert2rhel(
        "-y --serverurl {} -k {} -o {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_KEY"),
            env.str("RHSM_ORG"),
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
