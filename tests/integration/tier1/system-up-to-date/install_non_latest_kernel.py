import platform


system_version = platform.platform()


def handle_oralce8(shell):
    """
    On Oracle Linux 8.4 the repo contains only one kernel,
    so we have to try to install kernel from older repo.

    """
    ol84_url = "baseurl = https://yum.oracle.com/repo/OracleLinux/OL8/4/baseos/base/x86_64/"
    ol83_url = "baseurl = https://yum.oracle.com/repo/OracleLinux/OL8/3/baseos/base/x86_64/"
    if "oracle-8.4" in system_version:
        with open("/etc/yum.repos.d/oracle-linux-ol8.repo", "r") as file:
            file_content = file.read()
            # replace 8.4 url to 8.3
            file_content = file_content.replace(ol84_url, ol83_url)
        with open("/etc/yum.repos.d/oracle-linux-ol8.repo", "w") as file:
            file.write(file_content)

    assert shell("yum install kernel-4.18.0-240.el8 -y").returncode == 0
    shell("grub2-set-default 'Oracle Linux Server (4.18.0-240.el8.x86_64) 8.3'")

    # restore original
    # TODO for fun, maybe we can try the conversion on 8.4 with 8.3 kernel?
    if "oracle-8.4" in system_version:
        with open("/etc/yum.repos.d/oracle-linux-ol8.repo", "r") as file:
            file_content = file.read()
            # replace 8.3 url to 8.4
            file_content = file_content.replace(ol83_url, ol84_url)
        with open("/etc/yum.repos.d/oracle-linux-ol8.repo", "w") as file:
            file.write(file_content)


def handle_centos8(shell):
    """
    Install non latest kernel for each version that is available in the repository.
    """

    if "centos-8.4" in system_version:
        assert shell("yum install kernel-4.18.0-305.3.1.el8 -y").returncode == 0
        shell("grub2-set-default 'CentOS Linux (4.18.0-305.3.1.el8.x86_64) 8'")
    elif "centos-8.5" in system_version:
        assert shell("yum install kernel-4.18.0-348.el8 -y").returncode == 0
        shell("grub2-set-default 'CentOS Linux (4.18.0-348.el8.x86_64) 8'")


def test_install_one_kernel(shell):
    """
    Install specific kernel version and configure
    the system to boot to it. The kernel version is not the
    latest one available in repositories.
    """

    # Set default kernel
    if "centos-7" in system_version:
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        shell("grub2-set-default 'CentOS Linux (3.10.0-1160.el7.x86_64) 7 (Core)'")
    elif "oracle-7" in system_version:
        assert shell("yum install kernel-3.10.0-1160.el7.x86_64 -y").returncode == 0
        shell("grub2-set-default 'Oracle Linux Server 7.9, with Linux 3.10.0-1160.el7.x86_64'")
    elif "centos-8" in system_version:
        handle_centos8(shell)
    elif "oracle-8" in system_version:
        handle_oralce8(shell)
