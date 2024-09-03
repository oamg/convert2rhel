from conftest import TEST_VARS


def test_rhsm_conversion(convert2rhel):
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
