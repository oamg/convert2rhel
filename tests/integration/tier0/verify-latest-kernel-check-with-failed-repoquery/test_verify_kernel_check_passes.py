import platform

import pytest


@pytest.mark.latest_kernel_check_with_failed_repoquery
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
