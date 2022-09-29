def test_verify_latest_kernel_check_passes_with_failed_repoquery(shell, convert2rhel):
    """
    This test verifies, that failed repoquery is handled correctly.
    Failed repoquery subsequently caused the latest kernel check to fail.
    Introduced fixes should get the process past the latest kernel check.
    """

    repopath = "/etc/yum.repos.d/beaker.repo"

    # Add a tainted repository with intentionally bad baseurl so the repoquery fails successfully.
    assert shell(f"touch {repopath}").returncode == 0
    assert (
        shell(
            "printf '[beaker-client]\nname=Beaker Client - Fedora36\nbaseurl=http://download.eng.bos.redhat.com/\nenabled=1\ngpgcheck=0' > /etc/yum.repos.d/beaker.repo"
        )
    ).returncode == 0

    # Run the conversion just past the latest kernel check, if successful, end the conversion there.
    with convert2rhel("--debug --no-rpm-va") as c2r:
        assert c2r.expect("Continue with the system conversion?", timeout=300) == 0
        c2r.sendline("y")
        assert c2r.expect("Continue with the system conversion?", timeout=300) == 0
        c2r.sendline("n")
    assert c2r.exitstatus != 0

    # Cleanup the tainted repository.
    assert shell(f"rm -f {repopath}").returncode == 0
