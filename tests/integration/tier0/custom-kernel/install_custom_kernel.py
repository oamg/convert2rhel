import platform

from envparse import env


def test_install_custom_kernel(shell):
    # We install CentOS kernel on Oracle Linux and vice versa to mimic the custom kernel
    # that is not signed by the running OS official vendor
    system_version = platform.platform()

    if "centos-7" in system_version:
        # Install dependency for kernel-uek
        assert (
            shell(
                "yum install https://yum.oracle.com/repo/OracleLinux/OL7/latest/x86_64/getPackage/linux-firmware-20200124-999.4.git1eb2408c.el7.noarch.rpm -y"
            ).returncode
            == 0
        )
        assert (
            shell(
                "yum install https://yum.oracle.com/repo/OracleLinux/OL7/UEKR6/x86_64/getPackage/kernel-uek-5.4.17-2011.0.7.el7uek.x86_64.rpm -y"
            ).returncode
            == 0
        )
        shell("grub2-set-default 'CentOS Linux (5.4.17-2011.0.7.el7uek.x86_64) 7 (Core)'")
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
