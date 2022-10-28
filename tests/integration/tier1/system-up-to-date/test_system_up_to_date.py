import os
import platform

from envparse import env


system_version = platform.platform()


def test_skip_kernel_check(shell, convert2rhel):
    """
    Test that it is possible to use env variable in some case to override
    the kernel check inhibitor. One of the way to allow this is to not have
    any kernel packages present in repos.
    """

    # Move all repos to other location, so it is not being used
    assert shell("mkdir /tmp/s_backup").returncode == 0
    assert shell("mv /etc/yum.repos.d/* /tmp/s_backup/").returncode == 0

    # EUS version use hardoced repos from c2r as well
    if "centos-8" in system_version:
        assert shell("mkdir /tmp/s_backup_eus").returncode == 0
        assert shell("mv /usr/share/convert2rhel/repos/* /tmp/s_backup_eus/").returncode == 0

    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        if "centos-7" in system_version or "oracle-7" in system_version:
            c2r.expect("Could not find any kernel from repositories to compare against the loaded kernel.")
        else:
            c2r.expect("Could not find any kernel-core from repositories to compare against the loaded kernel.")
    assert c2r.exitstatus != 0

    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"

    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Detected 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' environment variable")
        c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    # Clean up
    if "centos-8" in system_version:
        assert shell("mv /tmp/s_backup_eus/* /usr/share/convert2rhel/repos/").returncode == 0
    assert shell("mv /tmp/s_backup/* /etc/yum.repos.d/").returncode == 0


def test_system_not_updated(shell, convert2rhel):
    """
    System contains at least one package that is not updated to
    the latest version. The c2r has to display a warning message
    about that. Also not updated package it's version
    is locked. Display a warning about used version lock.
    """
    centos_8_pkg_url = "https://vault.centos.org/8.1.1911/BaseOS/x86_64/os/Packages/wpa_supplicant-2.7-1.el8.x86_64.rpm"

    if "centos-8" in system_version:
        # The dnf transaction calculation fails if the maximum number of kernels that can be installed has been reached:
        # "package kernel-4.18.0-348.23.1.el8_5.x86_64 requires kernel-core-uname-r = 4.18.0-348.23.1.el8_5.x86_64,
        #     but none of the providers can be installed"
        # To us now the only known solution is to remove the oldest kernel before proceeding.
        oldest_kernel = shell(
            "rpm -q --qf '%{BUILDTIME}\t%{EVR}.%{ARCH}\n' kernel | sort -n | head -1 | cut -f2"
        ).output.strip()
        assert shell("yum remove -y kernel*{0}".format(oldest_kernel)).returncode == 0

    # Try to downgrade two packages.
    # On CentOS-8 we cannot do the downgrade as the repos contain only the latest package version.
    # We need to install package from older repository as a workaround.
    if "centos-8" in system_version:
        assert shell("yum install -y {}".format(centos_8_pkg_url)).returncode == 0
    else:
        assert shell("yum install openldap wpa_supplicant -y").returncode == 0
        assert shell("yum downgrade openldap wpa_supplicant -y").returncode == 0

    assert shell("yum install -y yum-plugin-versionlock").returncode == 0
    assert shell("yum versionlock wpa_supplicant").returncode == 0

    # Run utility until the reboot
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        c2r.expect(r"WARNING - The system has \d+ package\(s\) not updated")
    assert c2r.exitstatus == 0
