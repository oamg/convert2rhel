import socket

import pytest

from conftest import SYSTEM_RELEASE_ENV
from envparse import env


def setup_proxy(shell):
    """
    Restrict the system internet connection only to a forward proxy server.
    This is done by setting up a firewall setting on the machine.
    Also for conversion to work it is necessary to enabled connection to specific
    URLs directly from the machine.
    """

    # Make sure the firewalld is installed, enabled and running
    shell("yum install -y firewalld")
    shell("systemctl enable --now firewalld")

    # As mentioned in the C2R documentation (https://url.corp.redhat.com/6d22a76)
    # the following hostnames needs to be reachable
    allowed_urls = [
        "ftp.redhat.com",
        "cdn-ubi.redhat.com",
        "cdn.redhat.com",
        "cdn-public.redhat.com",
        "subscription.rhsm.redhat.com",
        "static.redhat.com",
        "cert.console.redhat.com",
    ]
    for url in allowed_urls:
        ip_address = socket.gethostbyname(url)
        assert (
            shell(
                f"firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -m tcp -d {ip_address} --dport=443 -j ACCEPT"
            ).returncode
            == 0
        )
        assert (
            shell(
                f"firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -m tcp -d {ip_address} --dport=80 -j ACCEPT"
            ).returncode
            == 0
        )
    # Allow connection to the proxy server
    assert (
        shell(
            f"firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -m tcp --dport=3128 -j ACCEPT"
        ).returncode
        == 0
    )

    # Block all outgoing HTTP and HTTPS connections
    assert (
        shell(
            "firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -m tcp --dport=443 -j DROP"
        ).returncode
        == 0
    )
    assert (
        shell(
            "firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -m tcp --dport=80 -j DROP"
        ).returncode
        == 0
    )

    # Restart the firewall daemon
    shell("systemctl restart firewalld")


def configure_yum_proxy(shell):
    """Configure yum to use the proxy server"""
    shell(f"echo 'proxy=http://{env.str('PROXY_SERVER')}:{env.str('PROXY_PORT')}' >> /etc/yum.conf")


def setup_rhsm(shell):
    """
    Set up the RHSM according to the documentation.
    Shortened link to doc: https://url.corp.redhat.com/6d22a76
    """

    assert (
        shell(
            f"curl -o /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release https://www.redhat.com/security/data/fd431d51.txt --proxy http://{env.str('PROXY_SERVER')}:{env.str('PROXY_PORT')}"
        ).returncode
        == 0
    )
    if SYSTEM_RELEASE_ENV in ("centos-7", "oracle-7"):
        assert (
            shell(
                f"curl -o /etc/yum.repos.d/client-tools.repo https://ftp.redhat.com/redhat/client-tools/client-tools-for-rhel-7-server.repo --proxy http://{env.str('PROXY_SERVER')}:{env.str('PROXY_PORT')}"
            ).returncode
            == 0
        )
    # Adding the client tools repo on 8.5 CentOS makes the installation of the subscription-manager fail on dependency issue.
    # On CentOS 8.5 the package can be installed from the default BaseOS repository.
    elif "centos-8" not in SYSTEM_RELEASE_ENV:
        assert (
            shell(
                f"curl -o /etc/yum.repos.d/client-tools.repo https://ftp.redhat.com/redhat/client-tools/client-tools-for-rhel-8-x86_64.repo \
              --proxy http://{env.str('PROXY_SERVER')}:{env.str('PROXY_PORT')}"
            ).returncode
            == 0
        )

    # On Oracle Linux 7 a "rhn-client-tools" package may be present on
    # the system which prevents "subscription-manager" to be installed.
    if "oracle-7" in SYSTEM_RELEASE_ENV:
        shell("yum remove rhn-client-tools -y")

    shell("yum -y install subscription-manager subscription-manager-rhsm-certificates")

    shell(
        f"subscription-manager config --server.proxy_hostname={env.str('PROXY_SERVER')} --server.proxy_port={env.str('PROXY_PORT')}"
    )

    shell(
        f"subscription-manager register --activationkey={env.str('RHSM_KEY')} --org={env.str('RHSM_ORG')} --serverurl={env.str('RHSM_SERVER_URL')}"
    )

    shell(f"subscription-manager attach --pool {env.str('RHSM_POOL')}")


@pytest.mark.test_proxy_conversion
def test_proxy_conversion(shell, convert2rhel):
    """
    System is connected to the internet through a proxy server.
    Verify that the conversion is successful.
    """
    setup_proxy(shell)

    configure_yum_proxy(shell)

    setup_rhsm(shell)

    with convert2rhel("-y --debug") as c2r:
        c2r.expect("Conversion successful!")
    assert c2r.exitstatus == 0
