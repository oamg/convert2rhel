import os
import platform

from envparse import env


system_version = platform.platform()


def test_versionlock_on_pkg(shell, convert2rhel):
    """
    System contains one package that is not updated and it's version
    is locked. Display a warning about used version lock used.
    """
    centos_8_pkg_url = "https://vault.centos.org/8.1.1911/BaseOS/x86_64/os/Packages/wpa_supplicant-2.7-1.el8.x86_64.rpm"

    # Try to downgrade two packages
    # On CentOS-8 we cannot do downgrade as the repos contains only the latest package version.
    # To workaround this we need to install package from older repo.
    if "centos-8" in system_version:
        assert shell("yum install -y {}".format(centos_8_pkg_url)).returncode == 0
    else:
        assert shell("yum install openldap wpa_supplicant -y").returncode == 0
        assert shell("yum downgrade openldap wpa_supplicant -y").returncode == 0

    assert shell("yum install -y yum-plugin-versionlock").returncode == 0
    assert shell("yum versionlock wpa_supplicant").returncode == 0

    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        # TODO do we want to test the scenario where we have a package locked by this?
        c2r.expect("WARNING - YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    # Clean up
    assert shell("yum versionlock clear").returncode == 0


def test_skip_kernel_check(shell, convert2rhel):
    """
    Test that it is possible to use env variable in some case to override
    kernel check inhibitor. One of the way to allow this is to not have
    any kernel packages present in repos.
    """
    shell("mkdir /tmp/my_tmp && mv /etc/yum.repos.d/* /tmp/my_tmp")

    with convert2rhel(
        ("--no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        if "centos-7" in system_version or "oracle-7" in system_version:
            c2r.expect("Could not find any kernel from repositories to compare against the loaded kernel.")
        elif "centos-8" in system_version or "oracle-8" in system_version:
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
    shell("mv /tmp/my_tmp/* /etc/yum.repos.d/")


def test_system_not_updated(convert2rhel):
    """
    System contains at least one package that is not updated to
    the latest version. The c2r has to display a warning message
    about that.
    """

    # run utility until the reboot
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect(r"WARNING - The system has \d+ packages not updated.")
    assert c2r.exitstatus == 0
