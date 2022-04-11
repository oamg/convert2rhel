import platform


def test_install_one_kernel(shell):
    """
    Install specific kernel version and configure
    the system to boot to it. The kernel version is not the
    latest one available in repositories.
    """
    system_version = platform.platform()

    # set deafault kernel
    if "centos-7" in system_version:
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'")
    elif "oracle-7" in system_version:
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'")
    elif "centos-8" in system_version:
        assert shell("yum install kernel-4.18.0-240.22.1.el8_3 -y").returncode == 0
        shell("grub2-set-default 'CentOS Linux (4.18.0-240.22.1.el8_3.x86_64) 8'")
    elif "oracle-8" in system_version:
        assert shell("yum install kernel-4.18.0-240.22.1.el8_3 -y").returncode == 0
        shell("grub2-set-default 'Oracle Linux Server (4.18.0-240.22.1.el8_3.x86_64) 8.3'")
