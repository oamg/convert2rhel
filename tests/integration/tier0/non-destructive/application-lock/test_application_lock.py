import re

import pytest


@pytest.mark.test_simultaneous_runs
def test_simultaneous_runs(convert2rhel):
    """
    Verify that running convert2rhel locks out other instances.
    Additionally validate that the logfile did not get overwritten by the second invocation's output.
    1/ Invoke convert2rhel, wait on data collection acknowledgement prompt.
    2/ Invoke second instance of convert2rhel, observe warning and the utility exit.
    3/ Exit the first run of convert2rhel.
    4/ Validate that the logfile did not get overwritten by the second invocation's output.
    5/ Invoke third instance of convert2rhel; with the previous instances dead, the third instance should be allowed to run.
    6/ Exit the utility on the first prompt.
    """

    def _run_second_instance():
        """
        Helper function initiating a second simultaneous run of convert2rhel.
        Expect exit immediately.
        """
        with convert2rhel("--debug") as c2r_two:
            c2r_two.expect("Another copy of convert2rhel is running.")
        assert c2r_two.exitstatus == 1

    # Invoke a first instance
    with convert2rhel("--debug") as c2r_one:
        c2r_one.expect("Continue with the system conversion?")
        # Invoke the helper function with a second run
        _run_second_instance()
        # Exit the first run
        c2r_one.sendline("n")
    assert c2r_one.exitstatus == 1

    c2r_log = "/var/log/convert2rhel/convert2rhel.log"
    pattern = r"DEBUG - /var/run/lock/convert2rhel\.pid PID \d+ unlocked"
    # Verify the log file did not get replaced by the second utility invocation
    with open(c2r_log, "r") as logfile:
        data = logfile.read()
        assert re.search(pattern, data)

    # Run for the third time to make sure, the application lock is removed
    with convert2rhel("--debug") as c2r_three:
        c2r_three.expect("Continue with the system conversion?")
        c2r_three.sendline("n")
    assert c2r_three.exitstatus == 1
