import re
import socket

from conftest import SYSTEM_RELEASE_ENV, TEST_VARS


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
            f"curl -o /etc/pki/rpm-gpg/RPM-GPG-KEY-redhat-release https://www.redhat.com/security/data/fd431d51.txt \
                  --proxy http://{TEST_VARS['PROXY_SERVER']}:{TEST_VARS['PROXY_PORT']}",
            silent=True,
        ).returncode
        == 0
    )

    client_tools_repo = ""
    if re.match(r"^(centos|oracle)-7", SYSTEM_RELEASE_ENV):
        client_tools_repo = "client-tools-for-rhel-7-server.repo"
    elif re.match(r"^(alma|centos|oracle|rocky|stream)-8", SYSTEM_RELEASE_ENV):
        client_tools_repo = "client-tools-for-rhel-8.repo"
    elif re.match(r"^(alma|oracle|rocky|stream)-9", SYSTEM_RELEASE_ENV):
        client_tools_repo = "client-tools-for-rhel-9.repo"

    ct_repo_shell_call = f"curl -o /etc/yum.repos.d/client-tools.repo https://cdn-public.redhat.com/content/public/repofiles/{client_tools_repo} \
                    --proxy http://{TEST_VARS['PROXY_SERVER']}:{TEST_VARS['PROXY_PORT']}"

    assert shell(ct_repo_shell_call, silent=True).returncode == 0

    # On CentOS 8.5 we need to replace the $releasever in the url to 8.5,
    # otherwise the dnf will complain with dependency issues.
    if "centos-8" in SYSTEM_RELEASE_ENV:
        shell("sed -i 's#\$releasever#8.5#' /etc/yum.repos.d/client-tools.repo")

    # On Oracle Linux 7 a "rhn-client-tools" package may be present on
    # the system which prevents "subscription-manager" to be installed.
    # Run the yum install call with no obsoletes flag.
    shell("yum -y install --setopt=obsoletes=0 subscription-manager subscription-manager-rhsm-certificates")

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
