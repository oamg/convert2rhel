import pytest

from conftest import TEST_VARS


@pytest.mark.test_error_after_ponr
def test_error_after_ponr(convert2rhel, shell):
    """
    Test the log message is displayed to the user when there is a fail after PONR

    And and exit code is 1

    This test destroys the machine so there aren't after checks or a reboot
    """
    with convert2rhel(
        "--serverurl {} --username {} --password {} --pool {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
            TEST_VARS["RHSM_POOL"],
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        # Assert that we start rollback first
        c2r.expect("WARNING - The tool allows rollback of any action until this point")
        c2r.expect(
            "WARNING - By continuing all further changes on the system will need to be reverted manually by the user, if necessary"
        )
        c2r.expect("Continue with the system conversion?")

        shell('echo "proxy=localhost" >> /etc/yum.conf').returncode == 0
        c2r.sendline("y")

        c2r.expect("WARNING - The conversion process failed")
        c2r.expect(
            "The system is left in an undetermined state that Convert2RHEL cannot fix. The system might not be fully converted, and might incorrectly be reporting as a Red Hat Enterprise Linux machine"
        )
        c2r.expect(
            "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore the system from a backup"
        )

    assert c2r.exitstatus == 1
