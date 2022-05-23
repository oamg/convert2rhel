import json


def test_basic_conversion(shell):
    os_release = shell("cat /etc/os-release").output
    assert "Red Hat Enterprise Linux" in os_release


def test_correct_distro(shell):
    shell("cat /etc/migration-results")

    with open("/etc/migration-results") as json_file:
        json_data = json.load(json_file)
        source_distro = json_data["activities"][0]["source_os"]

    with open("/etc/system-release", "r") as sys_release:
        destination_distro = sys_release.read()

    if "Red Hat Enterprise Linux Server release 7.9 (Maipo)" in destination_distro:
        assert (
            source_distro == "CentOS Linux release 7.9.2009 (Core)"
            or source_distro == "Oracle Linux Server release 7.9"
        )
    elif "Red Hat Enterprise Linux release 8.4 (Ootpa)" in destination_distro:
        assert source_distro == "CentOS Linux release 8.4.2105" or source_distro == "Oracle Linux Server release 8.4"
    elif "Red Hat Enterprise Linux release 8.5 (Ootpa)" in destination_distro:
        assert source_distro == "CentOS Linux release 8.5.2111"
    elif "Red Hat Enterprise Linux release 8.6 (Ootpa)" in destination_distro:
        assert source_distro == "Oracle Linux Server release 8.6"
    else:
        assert False, "Unknown destination distro"
