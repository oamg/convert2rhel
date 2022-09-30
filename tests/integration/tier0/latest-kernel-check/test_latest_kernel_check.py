import configparser
from conftest import SYSTEM_RELEASE_ENV
import pytest


@pytest.mark.failed_repoquery
def test_verify_latest_kernel_check_passes_with_failed_repoquery(shell, convert2rhel):
    """
    This test verifies, that failed repoquery is handled correctly.
    Failed repoquery subsequently caused the latest kernel check to fail.
    Introduced fixes should get the process past the latest kernel check.
    """
    repofile = "broken_repo"
    centos_custom_reposdir = "/usr/share/convert2rhel/repos/"

    # Add a tainted repository with intentionally bad baseurl so the repoquery fails successfully.
    # For CentOS we are working with hardcoded repos in /usr/share/convert2rhel/repos/centos-8.{4,5}

    if "centos-8" in SYSTEM_RELEASE_ENV:
        shell(f"cp -r files/{repofile}.repo {centos_custom_reposdir}/{SYSTEM_RELEASE_ENV}/")
    shell(f"cp -r files/{repofile}.repo /etc/yum.repos.d/")

    # Run the conversion just past the latest kernel check, if successful, end the conversion there.
    with convert2rhel("--debug --no-rpm-va") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

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
    if "centos-8" in SYSTEM_RELEASE_ENV:
        assert shell(f"rm -f {centos_custom_reposdir}/{SYSTEM_RELEASE_ENV}/{repofile}.repo").returncode == 0
    assert shell(f"rm -f /etc/yum.repos.d/{repofile}.repo").returncode == 0


@pytest.mark.yum_excld_kernel
def test_latest_kernel_check_with_exclude_kernel_option(shell, convert2rhel):
    """
    Define `exclude=kernel` in /etc/yum.conf and verify, the conversion is not inhibited with:
    'CRITICAL - Could not find any kernel from repositories to compare against the loaded kernel.'
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
        config.set("main", "exclude", f"{pre_existing_value} kernel kernel-core")
    else:
        config.set("main", "exclude", "kernel kernel-core")

    with open(yum_config, "w") as configfile:
        config.write(configfile, space_around_delimiters=False)

    assert config.has_option("main", "exclude")
    assert exclude_option in config.get("main", "exclude")

    # Run the conversion and verify, that it goes past the latest kernel check
    # if so, inhibit the conversion
    with convert2rhel("-y --debug --no-rpm-va") as c2r:
        c2r.expect("Prepare: Check if the loaded kernel version is the most recent")
        assert c2r.expect("Convert: List third-party packages", timeout=300) == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus != 0

    # Clean up
    assert shell(f"mv {backup_dir}/yum.conf {yum_config}").returncode == 0
    assert shell(f"rm -r {backup_dir}").returncode == 0

    verify_config = configparser.ConfigParser()
    verify_config.read(yum_config)
    if verify_config.has_option("main", "exclude"):
        assert exclude_option not in verify_config.get("main", "exclude")
