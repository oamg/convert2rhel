import configparser
import os

import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


@pytest.fixture(scope="function")
def tainted_repository(shell):
    """
    Fixture
    Add a tainted repository with intentionally bad baseurl so the repoquery fails successfully.
    """
    repofile = "broken_repo"
    centos_custom_reposdir = "/usr/share/convert2rhel/repos"

    # For CentOS, we are working with hardcoded repos in /usr/share/convert2rhel/repos/centos-8.5
    if "centos-8" in SYSTEM_RELEASE_ENV:
        shell(f"cp -r files/{repofile}.repo {centos_custom_reposdir}/centos-8.5/")
    shell(f"cp -r files/{repofile}.repo /etc/yum.repos.d/")

    yield

    # Cleanup the tainted repository.
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell(f"rm -f {centos_custom_reposdir}/centos-8.5/{repofile}.repo").returncode == 0
    assert shell(f"rm -f /etc/yum.repos.d/{repofile}.repo").returncode == 0


@pytest.mark.test_failed_repoquery
def test_verify_latest_kernel_check_passes_with_failed_repoquery(convert2rhel, tainted_repository):
    """
    This test verifies, that failed repoquery is handled correctly.
    Failed repoquery subsequently caused the latest kernel check to fail.
    Introduced fixes should get the process past the latest kernel check.
    """
    # Run the conversion just past the latest kernel check, if successful, end the conversion there.
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect(
            "Couldn't fetch the list of the most recent kernels available in the repositories. Did not perform the loaded kernel check.",
            timeout=300,
        )
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0


@pytest.fixture(scope="function")
def yum_conf_exclude_kernel(shell):
    """
    Fixture.
    Define `exclude=kernel kernel-core` in /etc/yum.conf.
    """
    yum_config = "/etc/yum.conf"
    backup_dir = "/tmp/config-backup"
    config = configparser.ConfigParser()
    config.read(yum_config)
    exclude_option = "kernel kernel-core"

    assert shell(f"mkdir {backup_dir}").returncode == 0

    assert shell(f"cp {yum_config} {backup_dir}").returncode == 0
    # If there is already an `exclude` section, append to the existing value
    if config.has_option("main", "exclude"):
        pre_existing_value = config.get("main", "exclude")
        config.set("main", "exclude", f"{pre_existing_value} {exclude_option}")
    else:
        config.set("main", "exclude", exclude_option)

    with open(yum_config, "w") as configfile:
        config.write(configfile, space_around_delimiters=False)

    assert config.has_option("main", "exclude")
    assert exclude_option in config.get("main", "exclude")

    yield

    # Clean up
    assert shell(f"mv {backup_dir}/yum.conf {yum_config}").returncode == 0
    assert shell(f"rm -r {backup_dir}").returncode == 0

    verify_config = configparser.ConfigParser()
    verify_config.read(yum_config)
    if verify_config.has_option("main", "exclude"):
        assert exclude_option not in verify_config.get("main", "exclude")

    # Double-check the exclude option is not in any config
    find_exclude = shell("grep -rE '^exclude' --include='yum.conf' --include='dnf.conf' /etc/").output
    # If the exclude option is present remove it
    if exclude_option in find_exclude:
        for item in find_exclude.split("\n"):
            if item:
                file = item.split(":")[0]
                shell(f"sed -i '/^exclude/d' {file}")


@pytest.mark.test_yum_exclude_kernel
def test_latest_kernel_check_with_exclude_kernel_option(convert2rhel, yum_conf_exclude_kernel):
    """
    Verify, the conversion does not raise:
    'Could not find any kernel from repositories to compare against the loaded kernel.'
    When `exclude=kernel kernel-core` is defined in yum.conf
    Verify IS_LOADED_KERNEL_LATEST has succeeded is raised and terminate the utility.
    """
    # Run the conversion and verify that it proceeds past the latest kernel check
    # if so, interrupt the conversion
    with convert2rhel("-y --debug") as c2r:
        if c2r.expect("IS_LOADED_KERNEL_LATEST has succeeded") == 0:
            c2r.sendcontrol("c")
        else:
            assert AssertionError, "Utility did not raise IS_LOADED_KERNEL_LATEST has succeeded"

    assert c2r.exitstatus != 0


@pytest.fixture(scope="function")
def kernel(shell):
    """
    Install specific kernel version and configure
    the system to boot to it. The kernel version is not the
    latest one available in repositories.
    """

    if os.environ["TMT_REBOOT_COUNT"] == "0":
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
            if "alma-8.6" in SYSTEM_RELEASE_ENV:
                assert shell("yum install kernel-4.18.0-372.13.1.el8_6.x86_64 -y")
                shell("grub2-set-default 'AlmaLinux (4.18.0-372.13.1.el8_6.x86_64) 8.6 (Sky Tiger)'")
            else:
                assert shell("yum install kernel-4.18.0-477.10.1.el8_8.x86_64 -y")
                shell("grub2-set-default 'AlmaLinux (4.18.0-477.10.1.el8_8.x86_64) 8.8 (Sapphire Caracal)'")
        elif "rocky-8" in SYSTEM_RELEASE_ENV:
            if "rocky-8.6" in SYSTEM_RELEASE_ENV:
                assert shell("yum install kernel-4.18.0-372.13.1.el8_6.x86_64 -y")
                shell("grub2-set-default 'Rocky Linux (4.18.0-372.13.1.el8_6.x86_64) 8.6 (Green Obsidian)'")
            else:
                assert shell("yum install kernel-4.18.0-477.10.1.el8_8.x86_64 -y")
                shell("grub2-set-default 'Rocky Linux (4.18.0-477.10.1.el8_8.x86_64) 8.8 (Green Obsidian)'")

        shell("tmt-reboot -t 600")

    yield

    if os.environ["TMT_REBOOT_COUNT"] == "1":
        # We need to get the name of the latest kernel
        # present in the repositories

        # Install 'yum-utils' required by the repoquery command
        shell("yum install yum-utils -y")

        # Get the name of the latest kernel
        latest_kernel = shell(
            "repoquery --quiet --qf '%{BUILDTIME}\t%{VERSION}-%{RELEASE}' kernel 2>/dev/null | tail -n 1 | awk '{printf $NF}'"
        ).output

        # Get the full name of the kernel
        full_name = shell(
            "grubby --info ALL | grep \"title=.*{}\" | tr -d '\"' | sed 's/title=//'".format(latest_kernel)
        ).output

        # Set the latest kernel as the one we want to reboot to
        shell("grub2-set-default '{}'".format(full_name.strip()))

        # Reboot after clean-up
        shell("tmt-reboot -t 600")


@pytest.mark.test_non_latest_kernel_error
def test_non_latest_kernel_error(kernel, shell, convert2rhel):
    """
    System has non latest kernel installed.
    Verify the ERROR - (ERROR) IS_LOADED_KERNEL_LATEST.INVALID_KERNEL_VERSION is raised.
    """
    if os.environ["TMT_REBOOT_COUNT"] == "1":
        with convert2rhel(
            "-y --serverurl {} --username {} --password {} --pool {} --debug".format(
                env.str("RHSM_SERVER_URL"),
                env.str("RHSM_USERNAME"),
                env.str("RHSM_PASSWORD"),
                env.str("RHSM_POOL"),
            )
        ) as c2r:
            c2r.expect("Check if the loaded kernel version is the most recent")
            if c2r.expect("IS_LOADED_KERNEL_LATEST:INVALID_KERNEL_VERSION") == 0:
                c2r.sendcontrol("c")
            else:
                assert (
                    AssertionError
                ), "Utility did not raise: ERROR - (ERROR) IS_LOADED_KERNEL_LATEST.INVALID_KERNEL_VERSION"
        assert c2r.exitstatus != 0
