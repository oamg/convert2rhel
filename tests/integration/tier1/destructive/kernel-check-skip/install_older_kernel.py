from conftest import SYSTEM_RELEASE_ENV
from test_helpers.workarounds import workaround_hybrid_rocky_image


def test_install_non_latest_kernel(shell, workaround_hybrid_rocky_image):
    """
    Install specific kernel version and configure
    the system to boot to it. The kernel version is not the
    latest one available in repositories.
    """

    # TODO(danmyway) test for latest minor only
    #  We can use grub2-reboot to utilize the one-time boot
    #  ( source <(grubby --info $(grubby --default-kernel)); echo "'$title'"; ) to get the original_kernel_title
    #  install older kernel
    #  ( source <(grubby --info $(grubby --default-kernel)); echo "'$title'"; ) to get the older_kernel_title
    #  grub2-set-default original_kernel_title
    #  grub2-reboot older_kernel_title

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
    elif "alma-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install --releasever=8.8 kernel-4.18.0-477.10.1.el8_8.x86_64 -y").returncode == 0
        shell("grub2-set-default 'AlmaLinux (4.18.0-477.10.1.el8_8.x86_64) 8.8 (Sapphire Caracal)'")
    elif "rocky-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install --releasever=8.8 kernel-4.18.0-477.10.1.el8_8.x86_64 -y").returncode == 0
        shell("grub2-set-default 'Rocky Linux (4.18.0-477.10.1.el8_8.x86_64) 8.8 (Green Obsidian)'")
    elif "stream-8" in SYSTEM_RELEASE_ENV:
        assert shell("yum install kernel-4.18.0-547.el8.x86_64 -y").returncode == 0
        shell("grub2-set-default 'CentOS Stream (kernel-4.18.0-547.el8.x86_64) 8'")
