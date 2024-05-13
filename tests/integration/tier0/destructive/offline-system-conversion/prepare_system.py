import os
import socket

import pytest

from conftest import TEST_VARS


def configure_connection():
    """
    Configure and limit connection to the satellite server only
    """
    satellite_ip = socket.gethostbyname(TEST_VARS["SATELLITE_URL"])
    # Get fully qualified domain name for the Satellite URL
    # With this we can disable the nameservers without the need to rely on resolving the hostname alias
    satellite_fqdn = socket.getfqdn(TEST_VARS["SATELLITE_URL"])

    with open("/etc/dnsmasq.conf", "a") as f:
        # Satellite url
        f.write("address=/{}/{}\n".format(satellite_fqdn, satellite_ip))

        # Everything else is resolved to localhost
        f.write("address=/#/127.0.0.1")

    with open("/etc/resolv.conf", "w") as f:
        f.write("nameserver 127.0.0.1")


@pytest.mark.prepare_offline_system
def test_prepare_system(shell, satellite_registration):
    """
    Perform all the steps to make the system appear to be offline.
    Register to the Satellite server.
    Remove all the repositories before the Satellite subscription,
    so there is only the redhat.repo created by subscription-manager.
    """
    assert shell("yum install dnsmasq -y").returncode == 0

    repos_dir = "/etc/yum.repos.d"
    # Remove all repofiles except the redhat.repo
    for file in os.listdir(repos_dir):
        if not file.endswith("redhat.repo"):
            os.remove(os.path.join(repos_dir, file))

    assert os.path.isfile("/etc/yum.repos.d/redhat.repo")

    configure_connection()

    assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0
