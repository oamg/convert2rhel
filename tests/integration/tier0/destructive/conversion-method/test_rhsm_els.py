import pytest

from conftest import TEST_VARS


@pytest.mark.test_rhsm_els_conversion
def test_rhsm_els_conversion(convert2rhel, shell, install_and_set_up_subman_to_stagecdn):
    """
    Verify that Convert2RHEL is working properly when ELS repositories are used during the conversion.
    Verify that the correct repositories are enabled after the conversion (in one of the check-after-conversion tests).
    """

    # Mark the system so the check for the enabled repos after the conversion handles this special case
    shell("touch /els_repos_used")

    with convert2rhel(
        "-y --username {} --password {} --debug --els".format(
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        c2r.expect_exact("Enabling RHEL repositories:")
        c2r.expect_exact("rhel-7-server-els-rpms")
        c2r.expect_exact("Conversion successful!")
    assert c2r.exitstatus == 0
