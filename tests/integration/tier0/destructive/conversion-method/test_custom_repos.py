from conftest import SYSTEM_RELEASE_ENV, SystemInformationRelease


def _assign_enable_repo_opt(shell):
    """
    Helper function.
    Assigns correct repositories to be enabled.
    Builds the full string with --enabelrepo/--enable <repo>
    :returns: enable_repo_opt_c2r, enable_repo_opt_yum
    :rtype: tuple(str,str)
    """
    system_version = SystemInformationRelease.version
    system_distribution = SystemInformationRelease.distribution
    repos = ("rhel-7-server-rpms", "rhel-7-server-optional-rpms", "rhel-7-server-extras-rpms")
    enable_opt_c2r = "--enablerepo"
    enable_opt_yum = "--enable"

    if system_version.major in (8, 9):
        # We want to go for EUS repositories only where really applicable
        #   1/ minor version matches EUS eligible version
        #   2/ the system distribution does snapshots of said versions
        #   3/ the current version is not the latest one available (i.e. not in the EUS phase yet)
        if system_version.minor in (4, 6, 8) and system_distribution != "oracle" and "latest" not in SYSTEM_RELEASE_ENV:
            repos = (
                f"rhel-{system_version.major}-for-x86_64-baseos-eus-rpms",
                f"rhel-{system_version.major}-for-x86_64-appstream-eus-rpms",
            )
            # Mark the system so the check for the enabled repos after the conversion handles this special case
            shell("touch /eus_repos_used")
        else:
            repos = (
                f"rhel-{system_version.major}-for-x86_64-baseos-rpms",
                f"rhel-{system_version.major}-for-x86_64-appstream-rpms",
            )

    enable_repo_opt_c2r = " ".join(f"{enable_opt_c2r} {repo}" for repo in repos)
    enable_repo_opt_yum = " ".join(f"{enable_opt_yum} {repo}" for repo in repos)

    return enable_repo_opt_c2r, enable_repo_opt_yum


def test_system_conversion_using_custom_repositories(shell, convert2rhel):
    """
    Conversion method with disabled subscription manager/RHSM and enabled 'custom' repositories.
    Usually we use the RHSM to enable the repositories `rhel-$releasever-server`.
    In this case we disable the RHSM and we need to provide our choice of repositories to be enabled.
    The repositories enabled in this scenario are
    {rhel7: [server rpms, extras rpms, optional rpms], rhel8: [[eus-]?baseos], [eus-]?appstream}.
    """

    enable_repo_opt_c2r, enable_repo_opt_yum = _assign_enable_repo_opt(shell)

    with convert2rhel("-y --no-rhsm {} --debug".format(enable_repo_opt_c2r)) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0

    shell("yum-config-manager {}".format(enable_repo_opt_yum))
