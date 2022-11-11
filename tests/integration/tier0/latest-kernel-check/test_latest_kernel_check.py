import configparser
import platform

import pytest


@pytest.mark.failed_repoquery
def test_verify_latest_kernel_check_passes_with_failed_repoquery(shell, convert2rhel):
    """
    This test verifies, that failed repoquery is handled correctly.
    Failed repoquery subsequently caused the latest kernel check to fail.
    Introduced fixes should get the process past the latest kernel check.
    """
    get_system_release = platform.platform()
    repofile = "broken_repo"
    centos_custom_reposdir = "/usr/share/convert2rhel/repos/"

    # Add a tainted repository with intentionally bad baseurl so the repoquery fails successfully.
    # For CentOS we are working with hardcoded repos in /usr/share/convert2rhel/repos/centos-8.{4,5}

    # TODO after the #619 gets merged, squash condition to centos-8 only
    # TODO and copy to {centos_custom_reposdir}/{get_system_release}/
    if "centos-8.4" in get_system_release:
        shell(f"cp -r files/{repofile}.repo {centos_custom_reposdir}/centos-8.4/")
    elif "centos-8.5" in get_system_release:
        shell(f"cp -r files/{repofile}.repo {centos_custom_reposdir}/centos-8.5/")
    shell(f"cp -r files/{repofile}.repo /etc/yum.repos.d/")

    # Run the conversion just past the latest kernel check, if successful, end the conversion there.
    with convert2rhel("--debug --no-rpm-va") as c2r:
        assert c2r.expect("Continue with the system conversion?", timeout=300) == 0
        c2r.sendline("y")
        assert (
            c2r.expect(
                "Couldn't fetch the list of the most recent kernels available in the repositories. Skipping the loaded kernel check.",
                timeout=300,
            )
            == 0
        )
        assert c2r.expect("Continue with the system conversion?", timeout=300) == 0
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Cleanup the tainted repository.
    if "centos-8.4" in get_system_release:
        assert shell(f"rm -f {centos_custom_reposdir}/centos-8.4/{repofile}.repo").returncode == 0
    if "centos-8.5" in get_system_release:
        assert shell(f"rm -f {centos_custom_reposdir}/centos-8.5/{repofile}.repo").returncode == 0
    assert shell(f"rm -f /etc/yum.repos.d/{repofile}.repo").returncode == 0


@pytest.mark.yum_exclude_kernel
def test_latest_kernel_check_with_exclude_kernel_option(shell, convert2rhel):
    """
    Define `exclude=kernel` in /etc/yum.conf and verify, the conversion is not inhibited with:
    CRITICAL - Could not find any kernel from repositories to compare against the loaded kernel.
    Please, check if you have any vendor repositories enabled to proceed with the conversion.
    """

    yum_config = "/etc/yum.conf"
    backup_dir = "/tmp/config-backup"
    config = configparser.ConfigParser()
    config.read(yum_config)
    exclude_option = "exclude=kernel\n"

    assert shell(f"mkdir {backup_dir}").returncode == 0

    assert shell(f"cp {yum_config} {backup_dir}").returncode == 0
    # If there is already an `exclude` section, append to the existing value
    if config.has_option("main", "exclude"):
        pre_existing_value = config.get("main", "exclude")
        config.set("main", "exclude", f"{pre_existing_value} kernel")
    else:
        config.set("main", "exclude", "kernel")

    with open(yum_config, "w") as configfile:
        config.write(configfile, False)

    assert exclude_option in shell(f"cat {yum_config}").output

    # Run the conversion and verify, that it goes past the latest kernel check
    # if so, inhibit the conversion
    with convert2rhel("-y --debug --no-rpm-va") as c2r:
        c2r.expect("Prepare: Checking if the installed packages are up-to-date")
        assert c2r.expect("Convert: List third-party packages", timeout=300) == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0

    # Clean up
    assert shell(f"mv {backup_dir}/yum.conf {yum_config}").returncode == 0
    assert shell(f"rm -r {backup_dir}").returncode == 0

    assert exclude_option not in shell(f"cat {yum_config}").output
