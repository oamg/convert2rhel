from conftest import TEST_VARS, SystemInformationRelease


def test_rhsm_with_eus_system_conversion(convert2rhel, shell):
    """
    Verify that Convert2RHEL is working properly when EUS repositories are used during the conversion.
    Only on EUS versions (8.6, 8.8, ...) it is possible to do EUS conversion.
    Verify that the correct repositories are enabled after the conversion.
    """

    # Mark the system so the check for the enabled repos after the conversion handles this special case
    shell("touch /eus_repos_used")

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug --eus".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        c2r.expect_exact("Enabling RHEL repositories:")
        c2r.expect_exact(f"rhel-{SystemInformationRelease.version.major}-for-x86_64-baseos-eus-rpms")
        c2r.expect_exact(f"rhel-{SystemInformationRelease.version.major}-for-x86_64-appstream-eus-rpms")
        c2r.expect_exact("Conversion successful!")
    assert c2r.exitstatus == 0
