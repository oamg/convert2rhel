def test_remove_kernel_pkg(shell):
    """
    This tests set's up the machine that it contains only kernel-core package on the system.
    Test is only viable to run on RHEL-8 like systems.
    """

    assert shell("yum install kernel-core -y").returncode == 0

    assert shell("yum remove kernel -y -x kernel-core").returncode == 0
