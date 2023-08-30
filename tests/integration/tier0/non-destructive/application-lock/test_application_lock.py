import pytest


@pytest.mark.test_simultaneous_runs
def test_simultaenous_runs(convert2rhel):
    """
    Verify that running convert2rhel locks out other instances.
    1/ Invoke convert2rhel, wait on data collection acknowledgement prompt.
    2/ Invoke second instance of convert2rhel, observe warning and the utility exit.
    3/ Exit the first run of convert2rhel.
    4/ Invoke third instance of convert2rhel; with the previous instances dead, the third instance should be allowed to run.
    5/ Exit the utility on the first prompt.
    """
    # Invoke a first instance
    with convert2rhel("--no-rpm-va --debug") as c2r_one:
        c2r_one.expect("Continue with the system conversion?")
        # Invoke a second run
        with convert2rhel("--no-rpm-va --debug") as c2r_two:
            c2r_two.expect("Another copy of convert2rhel is running.")
            assert c2r_two.exitstatus == 1
        c2r_one.sendline("n")
        assert c2r_one.exitstatus == 1
    # Invoke a third run
    with convert2rhel("--no-rpm-va --debug") as c2r_three:
        c2r_three.expect("Continue with the system conversion?")
        c2r_three.sendline("n")
        assert c2r_three.exitstatus == 1
