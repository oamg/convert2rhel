from envparse import env


def _modify_dnsmasq():
    with open("/etc/dnsmasq.conf", "a") as f:
        # Everything else is resolved to localhost
        f.write("address=/#/127.0.0.1")

    with open("/etc/resolv.conf", "w") as f:
        f.write("nameserver 127.0.0.1")


def _remove_changes_from_dnsmasq():
    """Delete only the last line that was appended to both files."""
    with open("/etc/dnsmas.conf", "r+") as f:
        lines = f.readlines()
        f.seek(0)
        f.truncate()
        f.writelines(lines[1:])

    with open("/etc/resolv.conf", "w") as f:
        lines = f.readlines()
        f.seek(0)
        f.truncate()
        f.writelines(lines[1:])


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
    _modify_dnsmasq()
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

    _remove_changes_from_dnsmasq()
    assert c2r.exitstatus == 1
