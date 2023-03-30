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
from convert2rhel.actions.system_checks import dbus


@pytest.fixture
def dbus_is_running_action():
    return dbus.DbusIsRunning()


@pytest.mark.parametrize(
    ("no_rhsm", "dbus_running", "log_msg"),
    (
        (True, True, "Skipping the check because we have been asked not to subscribe this system to RHSM."),
        (True, False, "Skipping the check because we have been asked not to subscribe this system to RHSM."),
        (False, True, "DBus Daemon is running"),
    ),
)
def test_check_dbus_is_running(
    caplog, monkeypatch, global_tool_opts, global_system_info, no_rhsm, dbus_running, log_msg, dbus_is_running_action
):
    monkeypatch.setattr(dbus, "tool_opts", global_tool_opts)
    global_tool_opts.no_rhsm = no_rhsm
    monkeypatch.setattr(dbus, "system_info", global_system_info)
    global_system_info.dbus_running = dbus_running

    dbus_is_running_action.run()
    unit_tests.assert_actions_result(dbus_is_running_action, status="SUCCESS")
    assert caplog.records[-1].message == log_msg


def test_check_dbus_is_running_not_running(monkeypatch, global_tool_opts, global_system_info, dbus_is_running_action):
    monkeypatch.setattr(dbus, "tool_opts", global_tool_opts)
    global_tool_opts.no_rhsm = False
    monkeypatch.setattr(dbus, "system_info", global_system_info)
    global_system_info.dbus_running = False

    dbus_is_running_action.run()

    unit_tests.assert_actions_result(
        dbus_is_running_action,
        status="ERROR",
        error_id="DBUS_DAEMON_NOT_RUNNING",
        message=(
            "Could not find a running DBus Daemon which is needed to"
            " register with subscription manager.\nPlease start dbus using `systemctl"
            " start dbus`"
        ),
    )
