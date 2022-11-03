import platform


def test_custom_kernel(convert2rhel):
    """

    Run the conversion with custom kernel installed on the system.

    """
    get_system_release = platform.platform()

    if "centos" in get_system_release:
        string = "CentOS"
    elif "oracle" in get_system_release:
        string = "Oracle"
    if os.environ["TMT_REBOOT_COUNT"] == "0":
        install_custom_kernel(shell)
    elif os.environ["TMT_REBOOT_COUNT"] == "1":
        with convert2rhel(("--no-rpm-va --debug")) as c2r:
            c2r.expect("WARNING - Custom kernel detected. The booted kernel needs to be signed by {}".format(string))
            c2r.expect("CRITICAL - The booted kernel version is incompatible with the standard RHEL kernel.")
        assert c2r.exitstatus != 0

        # Restore the system.
        clean_up_custom_kernel(shell)
