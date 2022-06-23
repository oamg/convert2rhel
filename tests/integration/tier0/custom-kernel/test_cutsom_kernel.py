import platform

from envparse import env


def test_custom_kernel(convert2rhel):
    # Run c2r with --variant option
    system_version = platform.platform()

    if "centos-7" in system_version:
        string = "CentOS"
    elif "oracle-7" in system_version:
        string = "Oracle"

    with convert2rhel(("--no-rpm-va --debug")) as c2r:
        c2r.expect("WARNING - Custom kernel detected. The booted kernel needs to be signed by")
        c2r.expect("CRITICAL - The booted kernel version is incompatible with the standard RHEL kernel.")
    assert c2r.exitstatus != 0
