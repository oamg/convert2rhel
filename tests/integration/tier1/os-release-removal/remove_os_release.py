def test_missing_os_release(shell):
    """
    This test case verify that it's possible to do full conversion when /etc/os-release
    file is not present on the system.
    The reference PR: https://github.com/oamg/convert2rhel/pull/384

    Note that using the satellite as a mathod of conversion is not
    supported at the moment and will fail during the registration process.
    """
    assert shell("rm /etc/os-release").returncode == 0
    assert shell("find /etc/os-release").returncode == 1
