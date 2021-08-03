def test_dependency_packages(shell):
    os_release = shell("cat /etc/os-release").output
    assert "Red Hat Enterprise Linux" in os_release
