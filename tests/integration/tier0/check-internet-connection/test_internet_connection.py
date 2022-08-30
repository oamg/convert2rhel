import os
import shutil

from envparse import env


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

    with open("/etc/dnsmasq.conf", "a") as f:
        # Everything else is resolved to localhost
        f.write("address=/#/127.0.0.1\n")

    with open("/etc/resolv.conf", "a") as f:
        f.write("nameserver 127.0.0.1\n")


def _restore_configuration_files():
    """Restore the original files and remove the modified ones."""
    if os.path.exists(DNSMASQ_CONF_FILE):
        os.remove(DNSMASQ_CONF_FILE)
        shutil.move(DNSMASQ_CONF_BACKUP_FILE, DNSMASQ_CONF_FILE)

    if os.path.exists(RESOLV_CONF_FILE):
        os.remove(RESOLV_CONF_FILE)
        shutil.copy(RESOLV_CONF_BACKUP_FILE, RESOLV_CONF_FILE)


def test_check_if_internet_connection_is_reachable(convert2rhel):
    """Test if convert2rhel can access the internet."""
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Checking internet connectivity using address")
        assert c2r.expect_exact("Internet connection available.") == 0
        c2r.send(chr(3))

    assert c2r.exitstatus == 1


def test_check_if_internet_connection_is_not_reachable(convert2rhel):
    """Test a case where the internet connection is not reachable by any means."""
    _modify_configuration_files()
    with convert2rhel(
        ("-y --no-rpm-va --serverurl {} --username {} --password {} --pool {} --debug").format(
            env.str("RHSM_SERVER_URL"),
            env.str("RHSM_USERNAME"),
            env.str("RHSM_PASSWORD"),
            env.str("RHSM_POOL"),
        )
    ) as c2r:
        c2r.expect("Checking internet connectivity using address")
        c2r.expect("assuming no internet connection is present.")
        c2r.send(chr(3))

    _restore_configuration_files()
    assert c2r.exitstatus == 1
