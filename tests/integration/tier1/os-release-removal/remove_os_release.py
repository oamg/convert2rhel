def test_missing_os_release(shell):
    """
    This test case verify that it's possible to do full conversion when /etc/os-release
    file is not present on the system.
    """
    assert shell("rm /etc/os-release").returncode == 0
    assert shell("find /etc/os-release").returncode == 1
