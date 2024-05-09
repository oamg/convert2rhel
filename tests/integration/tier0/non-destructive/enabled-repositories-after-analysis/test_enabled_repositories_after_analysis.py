import pytest

from conftest import TEST_VARS


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
            enabled_repositories.append(repo_id)

    return enabled_repositories


@pytest.mark.test_enabled_repositories_after_analysis
def test_enabled_repositories_after_analysis(shell, convert2rhel, satellite_registration):
    """Test analysis systems not connected to the Internet but requiring sub-mgr (e.g. managed by Satellite).

    This test will perform the following operations:
        - Collect the enabled repositories prior to the analysis start
        - Run the analysis and assert that we successfully enabled the RHSM repositories
        - Collect the enabled repositories after the tool run to compare with the repositories prior to the analysis
    """
    enabled_repositories_prior_analysis = collect_enabled_repositories(shell)

    with convert2rhel("analyze -y --debug") as c2r:
        c2r.expect("Rollback: Enabling RHSM repositories")

    assert c2r.exitstatus == 0

    enabled_repositories_after_analysis = collect_enabled_repositories(shell)

    assert enabled_repositories_prior_analysis == enabled_repositories_after_analysis
