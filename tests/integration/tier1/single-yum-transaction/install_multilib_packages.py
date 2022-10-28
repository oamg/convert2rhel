import platform


system_version = platform.platform()


def test_install_multilib_packages(shell):
    """Install NTP package."""

    if "oracle-8" in system_version or "centos-8" in system_version:
        assert (
            shell(
                "yum install iwl7260-firmware accel-config*.i686 libreport-cli ModemManager* ModemManager*.i686 -y"
            ).returncode
            == 0
        )
