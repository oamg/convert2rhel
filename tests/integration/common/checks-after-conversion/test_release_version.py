import json

import pytest


@pytest.mark.test_conversion_sanity_rhel_in_os_release
def test_sanity_conversion(shell):
    """
    After conversion sanity check to verify, that Red Hat Enterprise Linux is present in /etc/os-release.
    """
    os_release = shell("cat /etc/os-release").output
    assert "Red Hat Enterprise Linux" in os_release


# Maps destination distro names to the source distro information we expect
# to have converted from.
DISTRO_CONVERSION_MAPPING = {
    "Red Hat Enterprise Linux Server release 7.9 (Maipo)": (
        {"id": "Core", "name": "CentOS Linux", "version": "7.9"},
        {"id": "null", "name": "Oracle Linux Server", "version": "7.9"},
    ),
    "Red Hat Enterprise Linux release 8.5 (Ootpa)": ({"id": "null", "name": "CentOS Linux", "version": "8.5"},),
    "Red Hat Enterprise Linux release 8.8 (Ootpa)": (
        {"id": "Sapphire Caracal", "name": "AlmaLinux", "version": "8.8"},
        {"id": "Green Obsidian", "name": "Rocky Linux", "version": "8.8"},
    ),
    "Red Hat Enterprise Linux release 8.9 (Ootpa)": (
        {"id": "null", "name": "Oracle Linux Server", "version": "8.9"},
        {"id": "Midnight Oncilla", "name": "AlmaLinux", "version": "8.9"},
        {"id": "Green Obsidian", "name": "Rocky Linux", "version": "8.9"},
    ),
}


@pytest.mark.test_correct_distro
def test_correct_distro():
    """
    Verify, that we landed on the correct system version.
    """
    with open("/etc/migration-results") as json_file:
        json_data = json.load(json_file)
        source_distro = json_data["activities"][-1]["source_os"]

    with open("/etc/system-release", "r") as sys_release:
        destination_distro = sys_release.read()

    for destination_distro_name, possible_source_distros in DISTRO_CONVERSION_MAPPING.items():
        if destination_distro_name in destination_distro:
            assert source_distro in possible_source_distros
            break
    else:
        # We did not find a known destination_distro
        assert False, "Unknown destination distro '%s'" % destination_distro
