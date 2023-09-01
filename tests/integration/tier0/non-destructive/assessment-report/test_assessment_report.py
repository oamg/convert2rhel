import pytest

from envparse import env
from pexpect import EOF


@pytest.mark.test_failures_and_skips_in_report
def test_failures_and_skips_in_report(convert2rhel):
    """
    Test if the assessment report contains the following headers and messages:

    Error header, skip header, success header.
    """
    with convert2rhel(
        "analyze --no-rpm-va --serverurl {} --username test --password test --pool a_pool --debug".format(
            env.str("RHSM_SERVER_URL"),
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Assert that we start rollback first
        assert c2r.expect("Rollback: RHSM-related actions") == 0

        # Then, verify that the analysis report is printed
        assert c2r.expect("Pre-conversion analysis report", timeout=600) == 0

        # Error header first
        assert c2r.expect("Must fix before conversion", timeout=600) == 0
        c2r.expect("SUBSCRIBE_SYSTEM::UNKNOWN_ERROR - Unable to register the system")

        # Skip header
        assert c2r.expect("Could not be checked due to other failures", timeout=600) == 0
        c2r.expect("ENSURE_KERNEL_MODULES_COMPATIBILITY::SKIP - Skipped")

        # Success header
        assert c2r.expect("No changes needed", timeout=600) == 0

    assert c2r.exitstatus == 0


@pytest.mark.test_successful_report
def test_successful_report(convert2rhel):
    """
    Test if the assessment report contains the following header: Success header.

    And does not contain: Error header, Skip header.
    """
    with convert2rhel(
        "analyze --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
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
        assert c2r.expect("Pre-conversion analysis report", timeout=600) == 0

        # Verify that only success header printed out, assert if error or skip header appears
        c2r_report_header_index = c2r.expect(
            ["No changes needed", "Must fix before conversion", "Could not be checked due to other failures"],
            timeout=300,
        )
        if c2r_report_header_index == 0:
            pass
        elif c2r_report_header_index == 1:
            assert AssertionError("Error header in the analysis report.")
        elif c2r_report_header_index == 2:
            assert AssertionError("Skip header in the analysis report.")

    assert c2r.exitstatus == 0


@pytest.mark.test_convert_successful_report
def test_convert_successful_report(convert2rhel):
    """
    Validate that calling the `convert` subcommand works.
    Verify the assessment report does not contain any of the following headers:
    Success header, Error header, Skip header.
    """
    with convert2rhel(
        "convert --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Refuse the full conversion at PONR
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

        # Assert that the utility starts the rollback first
        assert c2r.expect("Rollback: RHSM-related actions") == 0

        # Then, verify that the analysis report TASK header is printed
        assert c2r.expect("Pre-conversion analysis report", timeout=600) == 0

        # Verify that none of the headers is present, assert if it is present
        c2r_report_header_index = c2r.expect(
            [EOF, "No changes needed", "Must fix before conversion", "Could not be checked due to other failures"],
            timeout=300,
        )
        if c2r_report_header_index == 0:
            pass
        elif c2r_report_header_index == 1:
            assert AssertionError("Success header in the analysis report.")
        elif c2r_report_header_index == 2:
            assert AssertionError("Error header in the analysis report.")
        elif c2r_report_header_index == 3:
            assert AssertionError("Skip header in the analysis report.")

    # Exitstatus is 1 due to user cancelling the conversion
    assert c2r.exitstatus != 0
