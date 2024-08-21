import os
import socket

import pytest

from conftest import TEST_VARS, SystemInformationRelease, get_full_kernel_title, grub_setup_workaround


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
        f.write("address=/{}/{}\n".format(TEST_VARS["SATELLITE_URL"], satellite_ip))
        f.write("address=/{}/{}\n".format(satellite_fqdn, satellite_ip))

        # Everything else is resolved to localhost
        f.write("address=/#/127.0.0.1")

    with open("/etc/resolv.conf", "w") as f:
        f.write("nameserver 127.0.0.1")


@pytest.mark.prepare_isolated_system
def test_prepare_system(shell, fixture_satellite):
    """
    Perform all the steps to make the system appear to be offline.
    Register to the Satellite server.
    Remove all the repositories before the Satellite registration,
    so there is only the redhat.repo created by subscription-manager.
    The original system repositories are then used from the synced Satellite server.
    """
    assert shell("yum install dnsmasq -y").returncode == 0

    configure_connection()

    assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0

    # We need to update the system at this point instead of relying on the ansible playbook
    # run with the host set up.
    # We could remove all the system repositories before the update, but in case
    # there is also an update of the <system>-release package the repositories would get restored.
    # Therefore, we update the system with all repositories disabled enabling only the Satellite.
    # Additionally, we exclude the rhn-client-tools which consistently stubbornly obsoletes and replaces
    # the subscription-manager
    assert shell("yum update -y --disablerepo=* --enablerepo=Satellite_Engineering* -x rhn-client-tools")

    # We have deliberately skipped the ansible task setting the standard RHCK as a running kernel
    # during the host preparation. That is, so we do not end up with a kernel version
    # ahead of the one available on the Satellite server
    if SystemInformationRelease.distribution == "oracle":
        # The latest RHCK should be installed at this point already by the system update
        # Keep this just as a safety measure
        shell("yum install kernel -y --disablerepo=* --enablerepo=Satellite_Engineering*")
        latest_kernel = shell("rpm -q --last kernel | head -1 | cut -d ' ' -f1 | sed 's/kernel-//'").output.strip()
        default_kernel_title = get_full_kernel_title(shell, kernel=latest_kernel)
        grub_setup_workaround(shell)
        shell(f"grub2-set-default '{default_kernel_title.strip()}'")
        shell("grub2-mkconfig -o /boot/grub2/grub.cfg")

    repos_dir = "/etc/yum.repos.d"
    # At this point we can safely remove all the repofiles except the redhat.repo
    for file in os.listdir(repos_dir):
        os.remove(os.path.join(repos_dir, file))
        assert not os.path.isfile(os.path.join(repos_dir, file))

    # Clean the package manager metadata and the cache directory
    pkgmanager = "yum"
    if SystemInformationRelease.version.major >= 8:
        pkgmanager = "dnf"
    shell(f"{pkgmanager} clean all && rm -rf /var/cache/{pkgmanager}/*")
