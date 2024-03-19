import re

import pytest


@pytest.fixture(scope="function")
def block_the_internet_connection_check(shell):
    """
    Block the internet connection to the static.redhat.com
    that is being checked by the convert2rhel utility
    """
    shell("echo '127.0.0.1 static.redhat.com' >> /etc/hosts")

    yield

    # Clean up
    shell("sed -i '/127.0.0.1 static.redhat.com/d' /etc/hosts")


@pytest.mark.test_available_connection
def test_check_if_internet_connection_is_reachable(convert2rhel):
    """Test if convert2rhel can access the internet."""
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect(
            "Checking internet connectivity using address 'https://static.redhat.com/test/rhel-networkmanager.txt'"
        )
        assert c2r.expect("internet connection seems to be available", timeout=300) == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0


@pytest.mark.test_failed_internet_connection_check
def test_failed_internet_connection_check(convert2rhel, shell, block_the_internet_connection_check, pre_registered):
    """
    Make sure the internet connection check fails. The analysis should be able
    to finish without any further issues.
    """
    with convert2rhel("analyze -y --debug") as c2r:
        c2r.expect(
            "Checking internet connectivity using address 'https://static.redhat.com/test/rhel-networkmanager.txt'"
        )
        c2r.expect("There was a problem while trying to connect to")
        c2r.expect("Pre-conversion analysis report", timeout=600)

    # Check that there are no errors in the analysis report
    with open("/var/log/convert2rhel/convert2rhel.log", "r") as logfile:
        log_data = logfile.read()
        match = re.search(r"Error \(Must fix before conversion\)", log_data, re.IGNORECASE)
        assert match is None, "Error found in the log file data."

    assert c2r.exitstatus == 0
