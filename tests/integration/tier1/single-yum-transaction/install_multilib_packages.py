def test_install_multilib_packages(shell):
    """Install multilib packages."""

    assert (
        shell(
            "yum install iwl7260-firmware accel-config*.i686 libreport-cli ModemManager* ModemManager*.i686 -y"
        ).returncode
        == 0
    )
