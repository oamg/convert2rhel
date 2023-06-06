from conftest import SYSTEM_RELEASE_ENV


def test_install_one_kernel(shell):
    """
    Install specific kernel version and configure
    the system to boot to it. The kernel version is not the
    latest one available in repositories.
    """

    # Set default kernel
    if "centos-7" in SYSTEM_RELEASE_ENV:
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'")
    elif "oracle-7" in SYSTEM_RELEASE_ENV:
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'")
    elif "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install kernel-4.18.0-348.el8 -y").returncode == 0
        shell("grub2-set-default 'CentOS Stream (4.18.0-348.el8.x86_64) 8'")
    # Test is being run only for the latest released oracle-linux
    elif "oracle-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install kernel-4.18.0-80.el8.x86_64 -y").returncode == 0
        shell("grub2-set-default 'Oracle Linux Server (4.18.0-80.el8.x86_64) 8.0'")
