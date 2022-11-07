from conftest import SYSTEM_RELEASE


def test_install_multilib_packages(shell):
    """Install NTP package."""

    if "oracle-8" in SYSTEM_RELEASE or "centos-8" in SYSTEM_RELEASE:
        assert (
            shell(
                "yum install iwl7260-firmware accel-config*.i686 libreport-cli ModemManager* ModemManager*.i686 -y"
            ).returncode
            == 0
        )
