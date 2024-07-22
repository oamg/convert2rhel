import pytest


def test_check_firewalld_errors(shell):
    """Verify that there are no errors in firewalld"""
    if shell("rpm -q firewalld").returncode == 0:
        shell("systemctl start firewalld")
        assert shell("journalctl -u firewalld | grep -i ERROR").returncode == 1
    else:
        pytest.skip("Skipping because firewalld package is not present on system.")
