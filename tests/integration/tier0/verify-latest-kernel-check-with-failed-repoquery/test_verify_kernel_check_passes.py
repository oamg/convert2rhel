import pytest


@pytest.mark.latest_kernel_check_with_failed_repoquery
def test_verify_latest_kernel_check_passes_with_failed_repoquery(shell, convert2rhel):
    """
    This test verifies, that failed repoquery is handled correctly.
    Failed repoquery subsequently caused the latest kernel check to fail.
    Introduced fixes should get the process past the latest kernel check.
    """

    repopath = "/etc/yum.repos.d/tainted_repo.repo"
    tainted_repo_setup = "[tainted-repo]\nname=Tainted repository\nbaseurl=http://download.eng.bos.redhat.com/beakerrepos/client/Fedor36/\nenabled=1\ngpgcheck=0"

    # Add a tainted repository with intentionally bad baseurl so the repoquery fails successfully.
    with open(repopath, "w") as tainted_repo:
        tainted_repo.write(tainted_repo_setup)

    assert shell(f"cat {repopath}").output == tainted_repo_setup

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
    assert shell(f"rm -f {repopath}").returncode == 0
