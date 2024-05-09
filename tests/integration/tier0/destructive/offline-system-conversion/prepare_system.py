import os
import re
import socket

import pytest

from conftest import TEST_VARS


# def replace_urls_rhsm():
#     """
#     Replace urls in rhsm.conf file to the satellite server
#     Without doing this we get obsolete dogfood server as source of repositories
#     """
#     with open("/etc/rhsm/rhsm.conf", "r+") as f:
#         file = f.read()
#         # Replacing the urls
#         file = re.sub("hostname = .*", "hostname = {}".format(TEST_VARS["SATELLITE_URL"]), file)
#         file = re.sub("baseurl = .*", "baseurl = https://{}/pulp/repos".format(TEST_VARS["SATELLITE_URL"]), file)
#
#         # Setting the position to the top of the page to insert data
#         f.seek(0)
#         f.write(file)
#         f.truncate()


def configure_connection():
    """
    Configure and limit connection to the satellite server only
    """
    satellite_ip = socket.gethostbyname(TEST_VARS["SATELLITE_URL"])

    with open("/etc/dnsmasq.conf", "a") as f:
        # Satellite url
        f.write("address=/{}/{}\n".format(TEST_VARS["SATELLITE_URL"], satellite_ip))

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

    # replace_urls_rhsm()

    configure_connection()

    assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0
