import os
import re

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


def test_skip_kernel_check(shell, convert2rhel):
    """
    Test that it is possible to use env variable in some case to override
    the kernel check inhibitor. One of the way to allow this is to not have
    any kernel packages present in repos.
    """

    # Move all repos to other location, so it is not being used
    assert shell("mkdir /tmp/s_backup").returncode == 0
    assert shell("mv /etc/yum.repos.d/* /tmp/s_backup/").returncode == 0

    # EUS version use hardcoded repos from c2r as well
    if re.match(r"^(alma|rocky)-8\.6$", SYSTEM_RELEASE_ENV) or "centos-8-latest" in SYSTEM_RELEASE_ENV:
        assert shell("mkdir /tmp/s_backup_eus").returncode == 0
        assert shell("mv /usr/share/convert2rhel/repos/* /tmp/s_backup_eus/").returncode == 0

    os.environ["CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK"] = "1"

    with convert2rhel(
        "--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect("Detected 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' environment variable")
        c2r.sendcontrol("c")
    assert c2r.exitstatus != 0

    # Clean up
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell("mv /tmp/s_backup_eus/* /usr/share/convert2rhel/repos/").returncode == 0
    assert shell("mv /tmp/s_backup/* /etc/yum.repos.d/").returncode == 0


def test_system_not_updated(shell, convert2rhel):
    """
    System contains at least one package that is not updated to
    the latest version. The c2r has to display a warning message
    about that. Also, not updated package has its version locked.
    Display a warning about used version lock.
    """
    centos_8_pkg_url = "https://vault.centos.org/8.1.1911/BaseOS/x86_64/os/Packages/wpa_supplicant-2.7-1.el8.x86_64.rpm"

    if "centos-8" in SYSTEM_RELEASE_ENV:
        # Try to downgrade two packages.
        # On CentOS-8 we cannot do the downgrade as the repos contain only the latest package version.
        # We need to install package from older repository as a workaround.
        assert shell("yum install -y {}".format(centos_8_pkg_url)).returncode == 0
    else:
        # Add sqlite to be able to downgrade the package on Alma and Rocky Linux
        assert shell("yum install openldap wpa_supplicant sqlite -y").returncode == 0
        assert shell("yum downgrade openldap wpa_supplicant sqlite -y").returncode == 0

    assert shell("yum install -y yum-plugin-versionlock").returncode == 0
    assert shell("yum versionlock wpa_supplicant sqlite").returncode == 0

    # Run utility until the reboot
    with convert2rhel(
        "-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug".format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("WARNING - YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        c2r.expect(r"WARNING - The system has \d+ package\(s\) not updated")
    assert c2r.exitstatus == 0
