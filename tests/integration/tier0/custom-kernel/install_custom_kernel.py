import platform


def test_install_custom_kernel(shell):
    # Install CentOS kernel on Oracle Linux and vice versa to mimic the custom kernel
    # that is not signed by the running OS official vendor.
    system_version = platform.platform()

    if "centos-7" in system_version:
        assert (
            shell(
                "yum install https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/kernel-3.10.0-1160.76.1.0.1.el7.x86_64.rpm -y"
            ).returncode
            == 0
        )
        shell("grub2-set-default 'CentOS Linux (3.10.0-1160.76.1.0.1.el7.x86_64) 7 (Core)'")
    elif "oracle-7" in system_version:
        assert (
            shell(
                "yum install http://mirror.centos.org/centos/7/os/x86_64/Packages/kernel-3.10.0-1160.el7.x86_64.rpm -y"
            ).returncode
            == 0
        )
        shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'")
    elif "centos-8.4" in system_version:
        assert (
            shell(
                "yum install https://yum.oracle.com/repo/OracleLinux/OL8/4/baseos/base/x86_64/getPackage/kernel-core-4.18.0-305.el8.x86_64.rpm -y"
            ).returncode
            == 0
        )
        shell("grub2-set-default 'Oracle Linux Server (4.18.0-305.el8.x86_64) 8.4'")
    elif "centos-8.5" in system_version:
        assert (
            shell(
                "yum install https://yum.oracle.com/repo/OracleLinux/OL8/5/baseos/base/x86_64/getPackage/kernel-core-4.18.0-348.el8.x86_64.rpm -y"
            ).returncode
            == 0
        )
        shell("grub2-set-default 'Oracle Linux Server (4.18.0-348.el8.x86_64) 8.5'")
    elif "oracle-8" in system_version:
        # Install CentOS 8.5 kernel
        assert (
            shell(
                "yum install https://vault.centos.org/centos/8.5.2111/BaseOS/x86_64/os/Packages/kernel-core-4.18.0-348.7.1.el8_5.x86_64.rpm -y"
            ).returncode
            == 0
        )
        shell("grub2-set-default 'CentOS Linux (4.18.0-348.7.1.el8_5.x86_64) 8'")
