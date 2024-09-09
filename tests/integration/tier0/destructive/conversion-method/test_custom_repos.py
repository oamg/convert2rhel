from conftest import SystemInformationRelease, get_custom_repos_names


def test_system_conversion_using_custom_repositories(shell, convert2rhel):
    """
    Conversion method with disabled subscription manager/RHSM and enabled 'custom' repositories.
    Usually we use the RHSM to enable the repositories `rhel-$releasever-server`.
    In this case we disable the RHSM and we need to provide our choice of repositories to be enabled.
    The repositories enabled in this scenario are
    {rhel7: [server rpms, extras rpms, optional rpms], rhel8: [[eus-]?baseos], [eus-]?appstream}.
    """
    # Join the --enablerepo <repo> on whitespace
    enable_repo_opt_c2r = " ".join(f"--enablerepo {repo}" for repo in get_custom_repos_names())

    if SystemInformationRelease.is_eus:
        shell("touch /eus_repos_used")

    with convert2rhel("-y --no-rhsm {} --debug".format(enable_repo_opt_c2r)) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0

    enable_repo_opt_yum = " ".join(f"--enable {repo}" for repo in get_custom_repos_names())
    shell("yum-config-manager {}".format(enable_repo_opt_yum))
