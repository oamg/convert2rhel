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

from convert2rhel import actions, subscription, unit_tests
from convert2rhel.actions.system_checks import dbus


@pytest.fixture
def dbus_is_running_action():
    return dbus.DbusIsRunning()


@pytest.mark.parametrize(
    ("should_subscribe", "dbus_running", "log_msg"),
    (
        (False, True, "Skipping the check because we have been asked not to subscribe this system to RHSM."),
        (False, False, "Skipping the check because we have been asked not to subscribe this system to RHSM."),
        (True, True, "DBus Daemon is running"),
    ),
)
def test_check_dbus_is_running(
    caplog, monkeypatch, global_system_info, should_subscribe, dbus_running, log_msg, dbus_is_running_action
):
    monkeypatch.setattr(subscription, "should_subscribe", lambda: should_subscribe)
    monkeypatch.setattr(dbus, "system_info", global_system_info)
    global_system_info.dbus_running = dbus_running

    dbus_is_running_action.run()

    unit_tests.assert_actions_result(dbus_is_running_action, level="SUCCESS")
    assert caplog.records[-1].message == log_msg


def test_check_dbus_is_running_not_running(monkeypatch, global_system_info, dbus_is_running_action):
    monkeypatch.setattr(subscription, "should_subscribe", lambda: True)
    monkeypatch.setattr(dbus, "system_info", global_system_info)
    global_system_info.dbus_running = False

    dbus_is_running_action.run()

    unit_tests.assert_actions_result(
        dbus_is_running_action,
        level="ERROR",
        id="DBUS_DAEMON_NOT_RUNNING",
        description="The Dbus daemon is not running",
        diagnosis="Could not find a running DBus Daemon which is needed to register with subscription manager.",
        remediations="Please start dbus using `systemctl start dbus`",
    )


def test_check_dbus_is_running_info_message(monkeypatch, dbus_is_running_action):
    monkeypatch.setattr(subscription, "should_subscribe", lambda: False)

    dbus_is_running_action.run()

    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="DBUS_IS_RUNNING_CHECK_SKIP",
                title="Skipping the dbus is running check",
                description="Skipping the check because we have been asked not to subscribe this system to RHSM.",
                diagnosis=None,
                remediations=None,
            ),
        )
    )
    assert expected.issuperset(dbus_is_running_action.messages)
    assert expected.issubset(dbus_is_running_action.messages)
