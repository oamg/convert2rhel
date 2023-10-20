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


@oracle8
def test_check_firewalld_availability_is_running(
    pretend_os, check_firewalld_availability_is_running_action, monkeypatch, global_system_info
):
    monkeypatch.setattr(check_firewalld_availability, "system_info", global_system_info)
    monkeypatch.setattr(
        check_firewalld_availability.systeminfo, "is_systemd_managed_service_running", lambda name: True
    )
    global_system_info.id = "oracle"
    global_system_info.version = Version(8, 8)

    check_firewalld_availability_is_running_action.run()

    unit_tests.assert_actions_result(
        check_firewalld_availability_is_running_action,
        level="ERROR",
        id="FIREWALLD_DAEMON_RUNNING",
        title="Firewalld is running",
        description="Firewalld is running and can cause problems during the package replacement phase.",
        diagnosis="We've detected that firewalld unit is running and might cause system problems after the conversion is done.",
        remediation="Stop firewalld by using the `systemctl stop firewalld` command. This will prevent errors while convert2rhel replaces the system packages and the kernel, whoever, that might not prevent errors from appearing the firewalld logs after the conversion.",
    )


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
