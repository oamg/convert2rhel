import os


system_release = os.environ["SYSTEM_RELEASE"]


def test_install_ntp_and_remove_dependency(shell):
    """Install NTP package and remove one dependency."""

    if "oracle-7" in system_release:
        assert shell("yum install ntp -y").returncode == 0
        assert shell("rpm -e --nodeps autogen-libopts").returncode == 0
