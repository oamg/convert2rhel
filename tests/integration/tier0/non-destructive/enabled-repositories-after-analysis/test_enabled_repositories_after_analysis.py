import pytest


RHEL_CERTIFICATE_69_PEM = "/usr/share/convert2rhel/rhel-certs/69.pem"


def collect_enabled_repositories(shell):
    """
    Collect the enabled repositories through a subscription-manager call.

    This function will return a list of repositories enabled.
    """
    raw_output = shell("subscription-manager repos --list-enabled").output
    assert raw_output

    enabled_repositories = []
    for line in raw_output.splitlines():
        if line.startswith("Repo ID:"):
            # Get the repo_id as in that split it will be the last thing in the
            # array.
            repo_id = line.split("Repo ID:")[-1]
            enabled_repositories.append(repo_id.strip())

    return enabled_repositories


@pytest.mark.parametrize("fixture_satellite", ["RHEL7_AND_CENTOS7_SAT_REG"], indirect=True)
@pytest.mark.parametrize("rhel_repo_enabled", [False, True])
def test_enabled_repositories_after_analysis(
    shell, convert2rhel, fixture_satellite, remove_repositories, rhel_repo_enabled
):
    """Test analysis systems not connected to the Internet but requiring sub-mgr (e.g. managed by Satellite).

    This test will perform the following operations:
        - Collect the enabled repositories prior to the analysis start
        - Run the analysis and assert that we successfully enabled the RHSM repositories
        - Collect the enabled repositories after the tool run to compare with the repositories prior to the analysis
    """

    if rhel_repo_enabled:
        # To enable RHEL repos we also need to put the 69.pem certificate to the
        # appropriate location
        shell(f"cp {RHEL_CERTIFICATE_69_PEM} /etc/pki/product-default/")
        shell("subscription-manager repos --enable='rhel-7-server-rpms'")

    enabled_repositories_prior_analysis = collect_enabled_repositories(shell)

    with convert2rhel("analyze -y --debug") as c2r:
        c2r.expect("Enabling RHEL repositories:")
        c2r.expect("rhel-7-server-rpms")
        c2r.expect("Rollback: Restore state of the repositories")

    assert c2r.exitstatus == 0

    enabled_repositories_after_analysis = collect_enabled_repositories(shell)

    # Repositories can be listed in a different order than the one we captured
    # before the analysis.
    for repository in enabled_repositories_after_analysis:
        assert repository in enabled_repositories_prior_analysis

    if rhel_repo_enabled:
        shell("rm -f /etc/pki/product-default/69.pem")

    # No error reported in the log
    assert shell("grep ERROR '/var/log/convert2rhel/convert2rhel-pre-conversion.txt'").returncode == 1
