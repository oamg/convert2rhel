import json


def test_basic_conversion(shell):
    os_release = shell("cat /etc/os-release").output
    assert "Red Hat Enterprise Linux" in os_release


def test_correct_distro():
    """ "
    Check that we landed on the correct version
    """
    with open("/etc/migration-results") as json_file:
        json_data = json.load(json_file)
        source_distro = json_data["activities"][-1]["source_os"]

    with open("/etc/system-release", "r") as sys_release:
        destination_distro = sys_release.read()

    if "Red Hat Enterprise Linux Server release 7.9 (Maipo)" in destination_distro:
        assert source_distro == {"id": "Core", "name": "CentOS Linux", "version": "7.9"} or source_distro == {
            "id": "null",
            "name": "Oracle Linux Server",
            "version": "7.9",
        }
    elif "Red Hat Enterprise Linux release 8.4 (Ootpa)" in destination_distro:
        assert source_distro == {"id": "null", "name": "CentOS Linux", "version": "8.4"} or source_distro == {
            "id": "null",
            "name": "Oracle Linux Server",
            "version": "8.4",
        }
    elif "Red Hat Enterprise Linux release 8.5 (Ootpa)" in destination_distro:
        assert source_distro == {"id": "null", "name": "CentOS Linux", "version": "8.5"}
    elif "Red Hat Enterprise Linux release 8.6 (Ootpa)" in destination_distro:
        assert source_distro == {"id": "null", "name": "Oracle Linux Server", "version": "8.6"}
    else:
        assert False, "Unknown destination distro"
