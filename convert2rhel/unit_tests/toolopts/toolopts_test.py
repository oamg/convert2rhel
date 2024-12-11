# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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
import six

from convert2rhel import toolopts


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class MockConfig:
    SOURCE = None

    def __init__(self, source, **kwds):
        self.SOURCE = source
        for key, value in kwds.items():
            setattr(self, key, value)

    def run(self):
        pass


@pytest.mark.parametrize(
    ("config_sources",),
    (
        ([MockConfig(source="command line", serverurl=None, org="test", activation_key=None)],),
        ([MockConfig(source="command line", serverurl=None, org=None, activation_key="test")],),
        ([MockConfig(source="command line", serverurl=None, username="test", activation_key="test", org="blabla")],),
        # Multiple configs
        (
            [
                MockConfig(source="command line", serverurl=None, username="test", activation_key="test", org="blabla"),
                MockConfig(
                    source="configuration file",
                    username="test",
                    activation_key="test",
                    org="blabla",
                    outdated_package_check_skip=True,
                ),
            ],
        ),
    ),
)
def test_apply_cls_attributes(config_sources, monkeypatch):
    _handle_config_conflict_mock = mock.Mock()
    _handle_missing_options_mock = mock.Mock()
    monkeypatch.setattr(toolopts.ToolOpts, "_handle_config_conflict", _handle_config_conflict_mock)
    monkeypatch.setattr(toolopts.ToolOpts, "_handle_missing_options", _handle_missing_options_mock)

    tool_opts = toolopts.ToolOpts()
    tool_opts.initialize(config_sources)

    for config in config_sources:
        assert all(hasattr(tool_opts, key) for key in vars(config).keys() if key != "SOURCE")

    assert _handle_config_conflict_mock.call_count == 1
    assert _handle_missing_options_mock.call_count == 1


@pytest.mark.parametrize(
    (
        "config_sources",
        "expected_message",
        "expected_output",
    ),
    (
        # Multiple configs
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username="test",
                    org=None,
                    activation_key=None,
                    password="test",
                    no_rpm_va=None,
                ),
                MockConfig(
                    source="configuration file", username="config_test", org=None, activation_key=None, password=None
                ),
            ],
            "You have passed the RHSM username through both the command line and the"
            " configuration file. We're going to use the command line values.",
            {"username": "test"},
        ),
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org="test",
                    activation_key=None,
                    password=None,
                    no_rpm_va=None,
                ),
                MockConfig(
                    source="configuration file", username=None, org="config test", activation_key=None, password=None
                ),
            ],
            "You have passed the RHSM org through both the command line and the"
            " configuration file. We're going to use the command line values.",
            {"org": "test"},
        ),
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org=None,
                    activation_key="test",
                    password=None,
                    no_rpm_va=None,
                ),
                MockConfig(
                    source="configuration file", username=None, org=None, activation_key="config test", password=None
                ),
            ],
            "You have passed the RHSM activation key through both the command line and the"
            " configuration file. We're going to use the command line values.",
            {"activation_key": "test"},
        ),
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username="test",
                    org=None,
                    activation_key=None,
                    password="test",
                    no_rpm_va=None,
                ),
                MockConfig(
                    source="configuration file", username=None, org=None, activation_key=None, password="config test"
                ),
            ],
            "You have passed the RHSM password through both the command line and the"
            " configuration file. We're going to use the command line values.",
            {"password": "test"},
        ),
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org=None,
                    activation_key=None,
                    password="test",
                    no_rpm_va=None,
                ),
                MockConfig(
                    source="configuration file", username="test", org=None, activation_key="test", password=None
                ),
            ],
            "You have passed either the RHSM password or activation key through both the command line and"
            " the configuration file. We're going to use the command line values.",
            {"activation_key": None, "org": None},
        ),
    ),
)
def test_handle_config_conflicts(config_sources, expected_message, expected_output, monkeypatch, caplog):
    _handle_missing_options_mock = mock.Mock()
    monkeypatch.setattr(toolopts.ToolOpts, "_handle_missing_options", _handle_missing_options_mock)

    tool_opts = toolopts.ToolOpts()
    tool_opts.initialize(config_sources)

    assert _handle_missing_options_mock.call_count == 1

    assert expected_message in caplog.records[-1].message
    assert all(vars(tool_opts)[key] == value for key, value in expected_output.items())


@pytest.mark.parametrize(
    (
        "config_sources",
        "expected_message",
    ),
    (
        # CLI - password without username
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org=None,
                    activation_key=None,
                    password="test",
                    no_rpm_va=None,
                ),
                MockConfig(source="configuration file", username=None, org=None, activation_key=None, password=None),
            ],
            "You have passed the RHSM password without an associated username. Provide a username together"
            " with the password.",
        ),
        # Config File - password without username
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org=None,
                    activation_key=None,
                    password=None,
                    no_rpm_va=None,
                ),
                MockConfig(source="configuration file", username=None, org=None, activation_key=None, password="test"),
            ],
            "You have passed the RHSM password without an associated username. Provide a username together"
            " with the password.",
        ),
        # CLI - username without password
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username="test",
                    org=None,
                    activation_key=None,
                    password=None,
                    no_rpm_va=None,
                ),
                MockConfig(source="configuration file", username=None, org=None, activation_key=None, password=None),
            ],
            "You have passed the RHSM username without an associated password. Provide a password together"
            " with the username.",
        ),
        # Config File - username without password
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org=None,
                    activation_key=None,
                    password=None,
                    no_rpm_va=None,
                ),
                MockConfig(source="configuration file", username="test", org=None, activation_key=None, password=None),
            ],
            "You have passed the RHSM username without an associated password. Provide a password together"
            " with the username.",
        ),
        (
            [
                MockConfig(
                    source="command line",
                    serverurl=None,
                    username=None,
                    org=None,
                    activation_key="test",
                    password="test",
                    no_rpm_va=None,
                ),
                MockConfig(source="configuration file", username=None, org=None, activation_key=None, password=None),
            ],
            "Either a password or an activation key can be used for system registration."
            " We're going to use the activation key.",
        ),
    ),
)
def test_handle_config_conflicts_only_warnings(config_sources, expected_message, monkeypatch, caplog):
    _handle_missing_options_mock = mock.Mock()
    monkeypatch.setattr(toolopts.ToolOpts, "_handle_missing_options", _handle_missing_options_mock)

    tool_opts = toolopts.ToolOpts()
    tool_opts.initialize(config_sources)

    assert _handle_missing_options_mock.call_count == 1

    assert expected_message in caplog.records[-1].message


@pytest.mark.parametrize(
    ("config_sources",),
    (
        (
            [
                MockConfig(
                    source="command line",
                    activity="conversion",
                    username=None,
                    org=None,
                    activation_key=None,
                    password=None,
                    no_rpm_va=True,
                    serverurl=None,
                ),
                MockConfig(
                    source="configuration file",
                    username=None,
                    org=None,
                    activation_key=None,
                    password=None,
                    incomplete_rollback=False,
                ),
            ],
        ),
    ),
)
def test_handle_config_conflicts_system_exit(config_sources):
    tool_opts = toolopts.ToolOpts()

    with pytest.raises(
        SystemExit,
        match=(
            "We need to run the 'rpm -Va' command to be able to perform a complete rollback of changes"
            " done to the system during the pre-conversion analysis. If you accept the risk of an"
            " incomplete rollback, set the incomplete_rollback option in the /etc/convert2rhel.ini"
            " config file to true. Otherwise, remove the --no-rpm-va option."
        ),
    ):
        tool_opts.initialize(config_sources)


@pytest.mark.parametrize(
    ("config_sources",),
    (
        ([MockConfig(source="command line", serverurl=None, org="test", activation_key=None)],),
        ([MockConfig(source="command line", serverurl=None, org=None, activation_key="test")],),
    ),
)
def test_handle_missing_options(config_sources):
    tool_opts = toolopts.ToolOpts()
    with pytest.raises(
        SystemExit,
        match="Either the --org or the --activationkey option is missing. You can't use one without the other.",
    ):
        tool_opts.initialize(config_sources)
