from conftest import SystemInformationRelease


def test_system_conversion_using_custom_repositories(shell, convert2rhel):
    """
    Conversion method with disabled subscription manager/RHSM and enabled 'custom' repositories.
    Usually we use the RHSM to enable the repositories `rhel-$releasever-server`.
    In this case we disable the RHSM and we need to provide our choice of repositories to be enabled.
    The repositories enabled in this scenario are
    {rhel7: [server rpms, extras rpms, optional rpms], rhel8: [[eus-]?baseos], [eus-]?appstream}.
    """

    with open("/etc/system-release", "r") as file:
        system_version = SystemInformationRelease.version
        enable_repo_opt = "--enablerepo rhel-7-server-rpms --enablerepo rhel-7-server-optional-rpms --enablerepo rhel-7-server-extras-rpms"

        if system_version.major == 8:
            if system_version.minor == 8:
                enable_repo_opt = (
                    "--enablerepo rhel-8-for-x86_64-baseos-eus-rpms --enablerepo rhel-8-for-x86_64-appstream-eus-rpms"
                )
                # Mark the system so the check for the enabled repos after the conversion handles this special case
                shell("touch /eus_repos_used")
            else:
                enable_repo_opt = (
                    "--enablerepo rhel-8-for-x86_64-baseos-rpms --enablerepo rhel-8-for-x86_64-appstream-rpms"
                )
        if system_version.major == 9:
            if system_version.minor in (4, 6, 8):
                enable_repo_opt = (
                    "--enablerepo rhel-9-for-x86_64-baseos-eus-rpms --enablerepo rhel-9-for-x86_64-appstream-eus-rpms"
                )
                # Mark the system so the check for the enabled repos after the conversion handles this special case
                shell("touch /eus_repos_used")
            else:
                enable_repo_opt = (
                    "--enablerepo rhel-9-for-x86_64-baseos-rpms --enablerepo rhel-9-for-x86_64-appstream-rpms"
                )

    with convert2rhel("-y --no-rhsm {} --debug".format(enable_repo_opt)) as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0

    # after the conversion using custom repositories it is expected to enable repos by yourself
    if system_version.major == 7:
        enable_repo_opt = (
            "--enable rhel-7-server-rpms --enable rhel-7-server-optional-rpms --enable rhel-7-server-extras-rpms"
        )
    elif system_version.major == 8:
        if system_version.minor == 8:
            enable_repo_opt = "--enable rhel-8-for-x86_64-baseos-eus-rpms --enable rhel-8-for-x86_64-appstream-eus-rpms"
        else:
            enable_repo_opt = "--enable rhel-8-for-x86_64-baseos-rpms --enable rhel-8-for-x86_64-appstream-rpms"
    elif system_version.major == 9:
        if system_version.minor in (4, 6, 8):
            enable_repo_opt = "--enable rhel-9-for-x86_64-baseos-eus-rpms --enable rhel-9-for-x86_64-appstream-eus-rpms"
        else:
            enable_repo_opt = "--enable rhel-9-for-x86_64-baseos-rpms --enable rhel-9-for-x86_64-appstream-rpms"

    shell("yum-config-manager {}".format(enable_repo_opt))
