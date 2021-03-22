def test_basic_rhel_info(shell):
    res = shell("cat /etc/os-system")
    assert "Red Hat Enterprise Linux" in res.stdout.read()
