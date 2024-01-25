import pytest


@pytest.mark.test_verify_logging_is_not_duplicated
def test_verify_logging_is_not_duplicated():
    """
    Verify that the logfile does not contain duplicated lines.

    This function goes through the log file line by line
    and verifies the lines are unique and not duplicated.
    """
    log_file = "/var/log/convert2rhel/convert2rhel.log"
    with open(log_file, "r") as log_file_data:
        previous_line = None
        for line in log_file_data:
            line = line.strip()
            if line != "":
                assert line != previous_line

            previous_line = line.strip()
