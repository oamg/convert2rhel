import os


system_release = os.environ["SYSTEM_RELEASE"]


def test_install_multilib_packages(shell):
    """Install NTP package."""

    if "oracle-8" in system_release or "centos-8" in system_release:
        assert (
            shell(
                "yum install iwl7260-firmware accel-config*.i686 libreport-cli ModemManager* ModemManager*.i686 -y"
            ).returncode
            == 0
        )
