import os
import socket

import pytest

from conftest import TEST_VARS, SystemInformationRelease, grub_setup_workaround


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
def test_prepare_system(shell, satellite_registration):
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
    assert shell("yum update -y --disablerepo=* --enablerepo=Satellite_Engineering*")

    # We have deliberately skipped setting the standard RHCK as a running kernel ansible task during the host preparation
    # that is done, so we do not end up with kernel version ahead of the one available on the Satellite server
    if SystemInformationRelease.distribution == "oracle":
        shell("dnf install kernel")
        latest_kernel = shell("rpm -q --last kernel | head -1 | cut -d ' ' -f1 | sed 's/kernel-//'").output.rstrip()
        grub_setup_workaround(shell)
        shell(f"grub2-set-default /boot/vmlinuz-{latest_kernel}")
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
