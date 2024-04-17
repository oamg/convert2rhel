import pytest

from conftest import TEST_VARS


@pytest.mark.test_rhsm_non_eus_account_conversion
def test_rhsm_non_eus_account(convert2rhel):
    """
    Verify that Convert2RHEL is working properly when EUS repositories are not available for conversions
    to RHEL EUS minor versions (8.6, ...) and there are the correct
    repositories attached to the system after the conversion.
    """

    # Mark the system so the check for the enabled repos after the conversion handles this special case
    with open("/non_eus_repos_used", mode="a"):
        pass

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --pool {} --debug --eus".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_NON_EUS_POOL"],
        )
    ) as c2r:
        c2r.expect_exact("Error: 'rhel-8-for-x86_64-baseos-eus-rpms' does not match a valid repository ID.")
        c2r.expect_exact("Error: 'rhel-8-for-x86_64-appstream-eus-rpms' does not match a valid repository ID.")
        c2r.expect_exact("The RHEL EUS repositories are not possible to enable.")
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
