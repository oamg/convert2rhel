import platform

from envparse import env


def test_non_latest_kernel(shell, convert2rhel):
    """
    System has non latest kernel installed, thus the conversion
    has to be inhibited.
    """
    system_version = platform.platform()

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("The current kernel version loaded is different from the latest version in your repos.")
    assert c2r.exitstatus != 0

    # Clean up, need to reboot after
    # TODO this will probably want some dynamic function which will find the latest kernel version
    # available as the current solution can break later on different distro versions.
    if "centos-7" in system_version:
        shell("grub2-set-default 'CentOS Linux (3.10.0-1160.59.1.el7.x86_64) 7 (Core)'")
    elif "oracle-7" in system_version:
        shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.59.1.el7.x86_64'")
    elif "centos-8" in system_version:
        shell("grub2-set-default 'CentOS Linux (4.18.0-348.7.1.el8_5.x86_64) 8'")
    elif "oracle-8" in system_version:
        shell("grub2-set-default 'Oracle Linux Server (4.18.0-348.20.1.el8_5.x86_64) 8.5'")
