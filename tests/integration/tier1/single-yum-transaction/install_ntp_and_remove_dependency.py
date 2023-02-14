from conftest import SYSTEM_RELEASE_ENV


def test_install_ntp_and_remove_dependency(shell):
    """Install NTP package and remove one dependency."""

    if "oracle-7" in SYSTEM_RELEASE_ENV:
        assert shell("yum install ntp -y").returncode == 0
        assert shell("rpm -e --nodeps autogen-libopts").returncode == 0
