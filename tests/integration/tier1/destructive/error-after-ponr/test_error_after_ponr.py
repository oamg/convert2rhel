from conftest import TEST_VARS


def test_error_after_ponr(convert2rhel, shell):
    """
    Verify the improved explanatory log message is displayed to the user when a fail occurs
    after the point of no return. Also verify that the exit code is 2.

    This test destroys the machine so neither reboot nor any checks after conversion are called
    """
    assert shell("yum install dnsmasq -y").returncode == 0
    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_SCA_USERNAME"],
            TEST_VARS["RHSM_SCA_PASSWORD"],
        )
    ) as c2r:
        # Wait until Point of no return appears. Then block all the internet connection
        c2r.expect_exact("WARNING - The tool allows rollback of any action until this point.")
        c2r.expect_exact("Convert: Replace system packages")

        # Everything is resolved to localhost
        with open("/etc/dnsmasq.conf", "a") as f:
            f.write("address=/#/127.0.0.1")

        with open("/etc/resolv.conf", "w") as f:
            f.write("nameserver 127.0.0.1")

        assert shell("systemctl enable dnsmasq && systemctl restart dnsmasq").returncode == 0

        c2r.expect("WARNING - The conversion process failed")
        c2r.expect(
            "The system is left in an undetermined state that Convert2RHEL cannot fix. The system might not be fully converted, and might incorrectly be reporting as a Red Hat Enterprise Linux machine"
        )
        c2r.expect(
            "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore the system from a backup"
        )

    assert c2r.exitstatus == 2
