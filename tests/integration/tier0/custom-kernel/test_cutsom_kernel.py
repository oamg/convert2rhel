import platform


def test_custom_kernel(convert2rhel):
    """

    Run the conversion with custom kernel installed on the system.

    """
    system_version = platform.platform()

    if "centos" in system_version:
        string = "CentOS"
    elif "oracle" in system_version:
        string = "Oracle"

    with convert2rhel(("--no-rpm-va --debug")) as c2r:
        c2r.expect("WARNING - Custom kernel detected. The booted kernel needs to be signed by {}".format(string))
        c2r.expect("CRITICAL - The booted kernel version is incompatible with the standard RHEL kernel.")
    assert c2r.exitstatus != 0
