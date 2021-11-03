def test_yum_check(shell):
    # Run yum check after the conversion
    assert shell("yum check").returncode == 0
