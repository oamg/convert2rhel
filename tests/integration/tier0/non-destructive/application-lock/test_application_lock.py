import os
import shutil

import pytest


@pytest.mark.test_simultaneous_runs
def test_simultaenous_runs(convert2rhel):
    """Test that running convert2rhel locks out other instances."""

    with convert2rhel("--no-rpm-va --debug") as c2r_one:
        c2r_one.expect("Continue with the system conversion?")
        with convert2rhel("--no-rpm-va --debug") as c2r_two:
            c2r_two.expect("Another copy of convert2rhel is running.")
            assert c2r_two.exitstatus == 1
        c2r_one.sendline("n")
        assert c2r_one.exitstatus == 1

@pytest.mark.test_sequential_runs
def test_sequential_runs(convert2rhel):
    """Test that two convert2rhel instances can be run sequentially."""

    with convert2rhel("--no-rpm-va --debug") as c2r_one:
        c2r_one.expect("Continue with the system conversion?")
        c2r_one.sendline("n")
        assert c2r_one.exitstatus == 1
    with convert2rhel("--no-rpm-va --debug") as c2r_two:
        c2r_two.expect("Continue with the system conversion?")
        c2r_two.sendline("n")
        assert c2r_two.exitstatus == 1
