import os
import shutil

import pytest


# The original dnsmasq.conf file
DNSMASQ_CONF_FILE = "/etc/dnsmasq.conf"

# The original resolv.conf file
RESOLV_CONF_FILE = "/etc/resolv.conf"

# The backup file for dnsmasq, should be /etc/dnsmasq.conf.bk
DNSMASQ_CONF_BACKUP_FILE = "{0}.bk".format(DNSMASQ_CONF_FILE)

# The backup file for resolv, should be /etc/resolv.conf.bk
RESOLV_CONF_BACKUP_FILE = "{0}.bk".format(RESOLV_CONF_FILE)


def _modify_configuration_files():
    """Modify the configuration files and backup the original ones."""
    # Backup the dnsmasq and resolv files
    shutil.copy(DNSMASQ_CONF_FILE, DNSMASQ_CONF_BACKUP_FILE)
    shutil.copy(RESOLV_CONF_FILE, RESOLV_CONF_BACKUP_FILE)

    with open(DNSMASQ_CONF_FILE, "a") as f:
        # Everything is resolved to localhost
        f.write("address=/#/127.0.0.1")

    # Overwrite the file instead of appending a new line.
    with open(RESOLV_CONF_FILE, "w") as f:
        f.write("nameserver 127.0.0.1")


def _restore_configuration_files():
    """Restore the original files and remove the modified ones."""
    if os.path.exists(DNSMASQ_CONF_FILE):
        os.remove(DNSMASQ_CONF_FILE)
        shutil.move(DNSMASQ_CONF_BACKUP_FILE, DNSMASQ_CONF_FILE)

    if os.path.exists(RESOLV_CONF_FILE):
        os.remove(RESOLV_CONF_FILE)
        shutil.copy(RESOLV_CONF_BACKUP_FILE, RESOLV_CONF_FILE)


@pytest.mark.available_connection
def test_check_if_internet_connection_is_reachable(convert2rhel):
    """Test if convert2rhel can access the internet."""
    with convert2rhel("--no-rpm-va --debug") as c2r:
        c2r.expect("Checking internet connectivity using address")
        assert c2r.expect("internet connection seems to be available", timeout=300) == 0
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    assert c2r.exitstatus == 1


@pytest.mark.unavailable_connection
def test_check_if_internet_connection_is_not_reachable(convert2rhel, shell):
    """Test a case where the internet connection is not reachable by any means."""
    assert shell("yum install dnsmasq -y").returncode == 0

    _modify_configuration_files()

    assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0

    with convert2rhel("--no-rpm-va --debug") as c2r:
        c2r.expect("Checking internet connectivity using address")
        assert c2r.expect("There was a problem while trying to connect to", timeout=300) == 0
        c2r.expect("Continue with the system conversion?")
        c2r.sendline("n")

    _restore_configuration_files()
    assert c2r.exitstatus == 1
