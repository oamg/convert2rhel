def test_yum_check(shell):
    """
    After conversion check verifying yum check is able to finis without any issues.
    """
    assert shell("yum check").returncode == 0
