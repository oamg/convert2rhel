import os.path
import re

import jsonschema

from pexpect import EOF
from test_helpers.common_functions import load_json_schema
from test_helpers.vars import TEST_VARS


PRE_CONVERSION_REPORT_JSON = "/var/log/convert2rhel/convert2rhel-pre-conversion.json"
PRE_CONVERSION_REPORT_TXT = "/var/log/convert2rhel/convert2rhel-pre-conversion.txt"
PRE_CONVERSION_REPORT_JSON_SCHEMA = load_json_schema(path="../../../../../schemas/assessment-schema-1.2.json")


def _validate_report():
    """
    Helper function.
    Verify the report is created in /var/log/convert2rhel/convert2rhel-pre-conversion.json,
    and it corresponds to its respective schema.
    Additionally verify that the report is created as a .txt file.
    """
    # Validate the txt variant of the report exists
    assert os.path.exists(PRE_CONVERSION_REPORT_TXT)
    headers = "(ERROR|WARNING|OVERRIDABLE|INFO)"
    # assert any of the headers exists in the report data, validating it's not empty
    with open(PRE_CONVERSION_REPORT_TXT) as report_txt:
        report_data = report_txt.read()
        assert re.search(headers, report_data)

    report_data_json = load_json_schema(PRE_CONVERSION_REPORT_JSON)

    # If some difference between generated json and its schema invoke exception
    try:
        jsonschema.validate(instance=report_data_json, schema=PRE_CONVERSION_REPORT_JSON_SCHEMA)
    except Exception:
        print(report_data_json)
        raise


def test_failures_and_skips_in_report(convert2rhel):
    """
    Verify that the assessment report contains the following headers and messages:
    Error header, skip header, success header.
    Also verify the message severity ordering.

    Verify the report is created in /var/log/convert2rhel/convert2rhel-pre-conversion.json,
    and it corresponds to its respective schema.
    """
    with convert2rhel(
        "analyze --serverurl {} --username test --password test --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Assert that we start rollback first
        c2r.expect_exact("TASK - [Rollback:")

        # Then, verify that the analysis report is printed
        c2r.expect("Pre-conversion analysis report", timeout=600)

        # Verify the ordering and contents
        # of the skip and error header
        # Success header first
        c2r.expect_exact("Success (No changes needed)")

        # Info header
        c2r.expect_exact("Info (No changes needed)")

        # Warning header
        c2r.expect_exact("Warning (Review and fix if needed)")

        # Skip header
        c2r.expect_exact("Skip (Could not be checked due to other failures)", timeout=600)
        c2r.expect("ENSURE_KERNEL_MODULES_COMPATIBILITY::SKIP - Skipped")
        c2r.expect("Skipped because SUBSCRIBE_SYSTEM was not successful")

        # Error header
        c2r.expect_exact("Error (Must fix before conversion)", timeout=600)
        c2r.expect("SUBSCRIBE_SYSTEM::FAILED_TO_SUBSCRIBE_SYSTEM")
        c2r.expect("Diagnosis: System registration failed with error")

    assert c2r.exitstatus == 2

    _validate_report()


def test_successful_report(convert2rhel):
    """
    Test if the assessment report contains the following header: Success header.

    And does not contain: Error header, Skip header.
    """
    with convert2rhel(
        "analyze --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Assert that we start rollback first
        c2r.expect("Rollback: RHSM-related actions")

        # Then, verify that the analysis report is printed
        c2r.expect("Pre-conversion analysis report", timeout=600)

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
        else:
            assert AssertionError("Some unexpected string found in the report")

    assert c2r.exitstatus == 0

    _validate_report()


def test_convert_method_successful_report(convert2rhel):
    """
    Validate that calling the `convert` subcommand works.
    Verify the assessment report does not contain any of the following headers:
    Success header, Error header, Skip header.
    """
    with convert2rhel(
        "convert --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Refuse the full conversion at PONR
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

        # Assert that the utility starts the rollback first
        c2r.expect("Rollback: RHSM-related actions")

        # Then, verify that the analysis report TASK header is printed
        c2r.expect("Pre-conversion analysis report", timeout=600)

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
        else:
            assert AssertionError("No header found.")
    # Exitstatus is 1 due to user cancelling the conversion
    assert c2r.exitstatus == 1

    _validate_report()
