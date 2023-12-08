import os
import shutil

import pytest


@pytest.fixture(scope="function")
def configuration_files(shell):
    # The original dnsmasq.conf file
    dnsmasq_conf_file = "/etc/dnsmasq.conf"

    # The original resolv.conf file
    resolv_conf_file = "/etc/resolv.conf"

    # The backup file for dnsmasq, should be /etc/dnsmasq.conf.bk
    dnsmasq_conf_backup_file = "{0}.bk".format(dnsmasq_conf_file)

    # The backup file for resolv, should be /etc/resolv.conf.bk
    resolv_conf_backup_file = "{0}.bk".format(resolv_conf_file)

    # Modify the configuration files and backup the original ones."""
    assert shell("yum install dnsmasq -y").returncode == 0

    # Backup the dnsmasq and resolv files
    shutil.copy(dnsmasq_conf_file, dnsmasq_conf_backup_file)
    shutil.copy(resolv_conf_file, resolv_conf_backup_file)

    with open(dnsmasq_conf_file, "a") as f:
        # Everything is resolved to localhost
        f.write("address=/#/127.0.0.1")

    # Overwrite the file instead of appending a new line.
    with open(resolv_conf_file, "w") as f:
        f.write("nameserver 127.0.0.1")

    assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0

    yield

    # Restore the original files and remove the modified ones.
    if os.path.exists(dnsmasq_conf_file):
        os.remove(dnsmasq_conf_file)
        shutil.move(dnsmasq_conf_backup_file, dnsmasq_conf_file)

    if os.path.exists(resolv_conf_file):
        os.remove(resolv_conf_file)
        shutil.copy(resolv_conf_backup_file, resolv_conf_file)

    shell("yum remove -y dnsmasq")


@pytest.mark.test_available_connection
def test_check_if_internet_connection_is_reachable(convert2rhel):
    """Test if convert2rhel can access the internet."""
    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect(
            "Checking internet connectivity using address 'https://static.redhat.com/test/rhel-networkmanager.txt'"
        )
        assert c2r.expect("internet connection seems to be available", timeout=300) == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1


@pytest.mark.test_unavailable_connection
def test_check_if_internet_connection_is_not_reachable(convert2rhel, shell, configuration_files):
    """Test a case where the internet connection is not reachable by any means."""

    with convert2rhel("--debug") as c2r:
        # We need to get past the data collection acknowledgement.
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("y")

        c2r.expect(
            "Checking internet connectivity using address 'https://static.redhat.com/test/rhel-networkmanager.txt'"
        )
        assert c2r.expect("There was a problem while trying to connect to", timeout=300) == 0
        c2r.sendcontrol("c")

    assert c2r.exitstatus == 1
