import sys

from envparse import env


def test_satellite_conversion(shell, convert2rhel):
    # Remove subscription manager if installed
    assert shell("yum remove subscription-manager -y").returncode == 0

    # Install katello package
    pkg_url = "https://dogfood.sat.engineering.redhat.com/pub/katello-ca-consumer-latest.noarch.rpm"
    pkg_dst = "/usr/share/convert2rhel/subscription-manager/katello-ca-consumer-latest.noarch.rpm"
    assert shell("wget --no-check-certificate --output-document {} {}".format(pkg_dst, pkg_url)).returncode == 0

    with convert2rhel(
        ("-y --no-rpm-va -k {} -o {} --debug").format(
            env.str("SATELLITE_KEY"),
            env.str("SATELLITE_ORG"),
        )
    ) as c2r:
        pass
    assert c2r.exitstatus == 0
