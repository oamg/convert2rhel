from conftest import SYSTEM_RELEASE


def test_install_multilib_packages(shell):
    """Install NTP package."""

    if SYSTEM_RELEASE in ("oracle-8.7", "centos-8.5", "centos-8.4"):
        assert (
            shell(
                "yum install iwl7260-firmware accel-config*.i686 libreport-cli ModemManager* ModemManager*.i686 -y"
            ).returncode
            == 0
        )
