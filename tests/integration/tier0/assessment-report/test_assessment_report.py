import pytest

from envparse import env


@pytest.mark.test_failures_and_skips_in_report
def test_failures_and_skips_in_report(convert2rhel):
    """
    Test if the assessment report contains the following headers and messages:

    Error header, skip header, success header.
    """
    with convert2rhel(
        "--no-rpm-va --serverurl {} --username test --password test --pool a_pool --debug".format(
            env.str("RHSM_SERVER_URL"),
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Assert that we start rollback first
        assert c2r.expect("Rollback: RHSM-related actions") == 0

        # Then, verify that the analysis report is printed
        c2r.expect("Pre-conversion analysis report")

        # Error header first
        c2r.expect("Must fix before conversion")
        c2r.expect("SUBSCRIBE_SYSTEM_UNKNOWN_ERROR: Unable to register the system through subscription-manager.")

        # Skip header
        c2r.expect("Could not be checked due to other failures")
        c2r.expect("ENSURE_KERNEL_MODULES_COMPATIBILITY.SKIP: Skipped because SUBSCRIBE_SYSTEM was not successful")

        # Success header
        c2r.expect("No changes needed")

    assert c2r.exitstatus == 1


@pytest.mark.test_successfull_report
def test_successfull_report(convert2rhel):
    """
    Test if the assessment report contains the following header: Success header.

    And does not contain: Error header, skip header, success header.
    """
    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Assert that we start rollback first
        assert c2r.expect("Rollback: RHSM-related actions") == 0

        # Then, verify that the analysis report is printed
        c2r.expect("Pre-conversion analysis report")
        c2r.expect("No changes needed")

        # Assert that the following header does not exist in the log.
        assert not c2r.expect("Must fix before conversion")
        assert not c2r.expect("Could not be checked due to other failures")

    assert c2r.exitstatus == 1
