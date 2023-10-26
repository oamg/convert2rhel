# Copyright(C) 2023 Red Hat, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

__metaclass__ = type

import pytest

from convert2rhel import actions, unit_tests
from convert2rhel.actions.system_checks import check_firewalld_availability
from convert2rhel.systeminfo import Version
from convert2rhel.unit_tests.conftest import oracle8


@pytest.fixture
def check_firewalld_availability_is_running_action():
    return check_firewalld_availability.CheckFirewalldAvailability()


@pytest.mark.parametrize(
    ("major", "id"),
    (
        (7, "centos"),
        (7, "oracle"),
    ),
)
def test_check_firewalld_availability_not_supported_system(
    major, id, monkeypatch, global_system_info, check_firewalld_availability_is_running_action
):
    monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
    global_system_info.id = id
    global_system_info.version = Version(major, 0)

    check_firewalld_availability_is_running_action.run()

    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="CHECK_FIREWALLD_AVAILABILITY_SKIP",
                title="Skipping the check for firewalld availability.",
                description="Skipping the check as it is relevant only for Oracle Linux 8.8 and above.",
                diagnosis=None,
                remediation=None,
            ),
        )
    )
    assert expected.issuperset(check_firewalld_availability_is_running_action.messages)
    assert expected.issubset(check_firewalld_availability_is_running_action.messages)


@pytest.mark.parametrize(
    ("systemd_service_running", "modules_cleanup_config", "set_result"),
    (
        (True, True, True),
        (False, False, False),
        (False, True, False),
        (True, False, False),
    ),
)
@oracle8
def test_check_firewalld_availability_is_running(
    pretend_os,
    check_firewalld_availability_is_running_action,
    monkeypatch,
    global_system_info,
    systemd_service_running,
    modules_cleanup_config,
    set_result,
):
    monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
    monkeypatch.setattr(
        check_firewalld_availability.systeminfo,
        "is_systemd_managed_service_running",
        lambda name: systemd_service_running,
    )
    monkeypatch.setattr(
        check_firewalld_availability, "_check_for_modules_cleanup_config", lambda: modules_cleanup_config
    )
    global_system_info.id = "oracle"
    global_system_info.version = Version(8, 8)

    check_firewalld_availability_is_running_action.run()
    if set_result:
        unit_tests.assert_actions_result(
            check_firewalld_availability_is_running_action,
            level="ERROR",
            id="FIREWALLD_MODULESS_CLEANUP_ON_EXIT_CONFIG",
            title="Firewalld is set to cleanup modules after exit.",
            description="Firewalld running on Oracle Linux 8 can lead to a conversion failure.",
            diagnosis="We've detected that firewalld unit is running and that causes iptables and nftables failures on Oracle Linux 8 and under certain conditions it can lead to a conversion failure.",
            remediation=(
                "Set the option CleanupModulesOnExit in /etc/firewalld/firewalld.conf to no prior to running convert2rhel:\n"
                "1. sed -i -- 's/CleanupModulesOnExit=yes/CleanupModulesOnExit=no/g' /etc/firewalld/firewalld.conf\n"
                "You can change the option back to yes after the system reboot - that is after the system boots into the RHEL kernel."
            ),
        )
    else:
        pass


@oracle8
def test_check_firewalld_availability_not_running(
    pretend_os, check_firewalld_availability_is_running_action, caplog, monkeypatch, global_system_info
):
    monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
    monkeypatch.setattr(
        check_firewalld_availability.systeminfo, "is_systemd_managed_service_running", lambda name: False
    )
    global_system_info.id = "oracle"
    global_system_info.version = Version(8, 8)

    check_firewalld_availability_is_running_action.run()

    assert caplog.records[-1].message == "Firewalld is not running."


@pytest.fixture
def write_firewalld_mockup_config(tmpdir, request):
    config_file = tmpdir.join("firewalld.conf")
    content = request.param["content"] if request.param["content"] else ""
    config_file.write(content)
    return str(config_file)


@pytest.mark.parametrize(
    ("write_firewalld_mockup_config", "expected"),
    (
        (
            {
                "content": """
CleanupModulesOnExit=yes
"""
            },
            True,
        ),
        (
            {
                "content": """
# firewalld config file

DefaultZone=public

MinimalMark=100

CleanupOnExit=yes

Lockdown=no

IPv6_rpfilter=yes

IndividualCalls=no

LogDenied=off

AutomaticHelpers=system

AllowZoneDrifting=yes
"""
            },
            False,
        ),
        (
            {
                "content": """
# firewalld config file

AllowZoneDrifting=yes

CleanupModulesOnExit=yes
"""
            },
            True,
        ),
        (
            {"content": None},
            False,
        ),
    ),
    indirect=("write_firewalld_mockup_config",),
)
def test_is_modules_cleanup_enabled(monkeypatch, write_firewalld_mockup_config, expected):
    monkeypatch.setattr(check_firewalld_availability, "FIREWALLD_CONFIG_FILE", write_firewalld_mockup_config)
    assert check_firewalld_availability._is_modules_cleanup_enabled() == expected
