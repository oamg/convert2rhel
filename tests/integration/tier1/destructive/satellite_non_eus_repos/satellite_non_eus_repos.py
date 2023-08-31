from envparse import env


def test_missing_os_release(shell, convert2rhel):
    """
    This test case verify that it's possible to do full conversion when /etc/os-release
    file is not present on the system.
    """

    # Mark the system so the check for the enabled repos after the conversion handles this special case
    assert shell("touch /non_eus_repos_used").returncode == 0

    # Remove subscription manager if installed
    assert shell("yum remove subscription-manager -y").returncode == 0

    assert shell("yum install wget -y").returncode == 0

    # Install katello package
    pkg_url = "https://satellite.sat.engineering.redhat.com/pub/katello-ca-consumer-latest.noarch.rpm"
    pkg_dst = "/usr/share/convert2rhel/subscription-manager/katello-ca-consumer-latest.noarch.rpm"
    assert shell("wget --no-check-certificate --output-document {} {}".format(pkg_dst, pkg_url)).returncode == 0

    with convert2rhel(
        "-y --no-rpm-va -k {} -o {} --debug".format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        c2r.expect("WARNING - Some repositories are not available: rhel-8-for-x86_64-baseos-eus-rpms")
        c2r.expect("WARNING - Some repositories are not available: rhel-8-for-x86_64-appstream-eus-rpms")
