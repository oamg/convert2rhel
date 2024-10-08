import socket

from conftest import TEST_VARS, SubscriptionManager


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
        "cert.console.redhat.com",
        TEST_VARS["RHSM_STAGECDN"],  # For stage testing
        TEST_VARS["RHSM_SERVER_URL"],  # For stage testing
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
            "firewall-cmd --permanent --direct --add-rule ipv4 filter OUTPUT 0 -p tcp -m tcp --dport=3128 -j ACCEPT"
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
    shell(f"echo 'proxy=http://{TEST_VARS['PROXY_SERVER']}:{TEST_VARS['PROXY_PORT']}' >> /etc/yum.conf", silent=True)


def setup_rhsm(shell):
    """
    Set up the RHSM according to the documentation.
    Shortened link to doc: https://url.corp.redhat.com/6d22a76
    We don't use the pre_registered fixture on purpose, to validate
    that the procedure in official documentation works.
    More information in the following JIRA Comment (URL Shortened)
    https://url.corp.redhat.com/7a722af
    """

    assert (
        shell(
            f"curl -o /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release https://security.access.redhat.com/data/fd431d51.txt \
                  --proxy http://{TEST_VARS['PROXY_SERVER']}:{TEST_VARS['PROXY_PORT']}",
            silent=True,
        ).returncode
        == 0
    )

    # Add the client tools repository and install subscription-manager
    subman = SubscriptionManager()
    subman.remove_package(package_name="rhn-client-tools")
    subman.add_client_tools_repo()
    subman.install_package()

    shell(
        f"subscription-manager config --server.proxy_hostname={TEST_VARS['PROXY_SERVER']} --server.proxy_port={TEST_VARS['PROXY_PORT']}",
        silent=True,
    )

    shell(
        f"subscription-manager register --password={TEST_VARS['RHSM_SCA_PASSWORD']} --username={TEST_VARS['RHSM_SCA_USERNAME']} --serverurl={TEST_VARS['RHSM_SERVER_URL']}",
        hide_command=True,
    )

    shell(f"subscription-manager config --rhsm.baseurl=https://{TEST_VARS['RHSM_STAGECDN']}", silent=True)


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
