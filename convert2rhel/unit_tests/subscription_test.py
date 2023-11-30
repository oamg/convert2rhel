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

import errno

from collections import namedtuple

import dbus
import dbus.connection
import dbus.exceptions
import pytest
import six

from convert2rhel import backup, exceptions, pkghandler, subscription, toolopts, unit_tests, utils
from convert2rhel.systeminfo import EUS_MINOR_VERSIONS, Version, system_info
from convert2rhel.unit_tests import (
    PromptUserMocked,
    RegisterSystemMocked,
    RunSubprocessMocked,
    UnregisterSystemMocked,
    create_pkg_information,
    get_pytest_marker,
    run_subprocess_side_effect,
)
from convert2rhel.unit_tests.conftest import centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def mocked_rhsm_call_blocking(monkeypatch, request):
    rhsm_returns = get_pytest_marker(request, "rhsm_returns")
    if not rhsm_returns:
        rhsm_returns = namedtuple("Mark", ("args",))([None])

    fake_bus_obj = mock.Mock()
    fake_dbus_connection = mock.Mock(return_value=fake_bus_obj)

    monkeypatch.setattr(dbus, "SystemBus", mock.Mock())
    monkeypatch.setattr(dbus.connection, "Connection", fake_dbus_connection)

    fake_bus_obj.call_blocking = mock.Mock(side_effect=rhsm_returns.args[0])

    return fake_bus_obj.call_blocking


@pytest.fixture
def tool_opts(global_tool_opts, monkeypatch):
    monkeypatch.setattr(subscription, "tool_opts", global_tool_opts)
    return global_tool_opts


class TestRefreshSubscriptionInfo:
    def test_refresh_subscription_info(self, caplog, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        subscription.refresh_subscription_info()

        assert "subscription-manager has reloaded its configuration." == caplog.messages[-1]

    def test_refresh_subscription_info_fail(self, caplog, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=1))

        with pytest.raises(subscription.RefreshSubscriptionManagerError):
            subscription.refresh_subscription_info()


class TestNeededSubscriptionManagerPkgs:
    @pytest.mark.parametrize(
        ("rhel_version",),
        (
            (Version(7, 10),),
            (Version(8, 4),),
        ),
    )
    def test_needed_subscription_manager_already_installed(self, monkeypatch, global_system_info, rhel_version):
        global_system_info.version = rhel_version
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_information",
            mock.Mock(
                return_value=[
                    create_pkg_information(name="subscription-manager"),
                    create_pkg_information(name="subscription-manager-rhsm-certificates.x86_64"),
                    create_pkg_information(name="subscription-manager-rhsm"),
                    create_pkg_information(name="python3-subscription-manager-rhsm"),
                    create_pkg_information(name="python3-cloud-what"),
                    create_pkg_information(name="json-c.x86_64"),
                    create_pkg_information(name="python-syspurpose"),
                    create_pkg_information(name="other-package"),
                    create_pkg_information(name="centos-release"),
                ]
            ),
        )
        assert not subscription.needed_subscription_manager_pkgs()

    def test_needed_subscription_manager_pkgs_need_pkgs(self, monkeypatch, global_system_info):
        def fake_get_installed_pkg_information(pkg_name):
            # We want to return information for some but not all of the
            # packages that subscription-manager requires (and a few extraneous
            # ones as well)
            installed_pkgs = (
                "python3-subscription-manager-rhsm",
                "other-package",
                "centos-release",
            )
            return_values = {n: create_pkg_information(name=n) for n in installed_pkgs}

            try:
                return [return_values[pkg_name]]
            except KeyError:
                return []

        monkeypatch.setattr(
            pkghandler, "get_installed_pkg_information", mock.Mock(side_effect=fake_get_installed_pkg_information)
        )

        global_system_info.version = Version(8, 5)
        global_system_info.id = "centos"
        monkeypatch.setattr(subscription, "system_info", global_system_info)

        assert subscription.needed_subscription_manager_pkgs()

    @pytest.mark.parametrize(
        ("rhel_version", "json_c_i686", "pkg_list", "upgrade_deps"),
        (
            (
                Version(7, 10),
                True,
                ["subscription-manager"],
                set(),
            ),
            (
                Version(8, 5),
                True,
                ["subscription-manager"],
                {"python3-syspurpose", "json-c.x86_64", "json-c.i686"},
            ),
            (Version(8, 5), False, ["subscription-manager"], {"python3-syspurpose", "json-c.x86_64"}),
        ),
    )
    def test__dependencies_to_update(
        self, rhel_version, json_c_i686, pkg_list, upgrade_deps, monkeypatch, global_system_info
    ):
        global_system_info.version = rhel_version
        global_system_info.id = "centos"
        global_system_info.is_rpm_installed = lambda _: json_c_i686
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_information",
            mock.Mock(
                return_value=[
                    create_pkg_information(name="subscription-manager-rhsm-certificates.x86_64"),
                    create_pkg_information(name="python3-subscription-manager-rhsm"),
                    create_pkg_information(name="dnf-plugin-subscription-manager"),
                    create_pkg_information(name="other-package"),
                    create_pkg_information(name="centos-release"),
                ]
            ),
        )
        assert upgrade_deps == set(subscription._dependencies_to_update(pkg_list))

    def test__dependencies_to_update_no_pkgs(self, monkeypatch, global_system_info):
        global_system_info.version = Version(8, 5)
        global_system_info.id = "centos"
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_information",
            mock.Mock(
                return_value=[
                    create_pkg_information(name="subscription-manager-rhsm-certificates.x86_64"),
                    create_pkg_information(name="python3-subscription-manager-rhsm"),
                    create_pkg_information(name="dnf-plugin-subscription-manager"),
                    create_pkg_information(name="other-package"),
                    create_pkg_information(name="centos-release"),
                ]
            ),
        )
        assert [] == subscription._dependencies_to_update([])

    @pytest.mark.parametrize(
        (
            "version",
            "json_c_i686_installed",
            "pkgs_to_download",
        ),
        (
            (
                (7, 0),
                False,
                frozenset(
                    (
                        "subscription-manager",
                        "subscription-manager-rhsm-certificates",
                        "subscription-manager-rhsm",
                        "python-syspurpose",
                    )
                ),
            ),
            (
                (8, 0),
                False,
                frozenset(
                    (
                        "subscription-manager",
                        "subscription-manager-rhsm-certificates",
                        "python3-subscription-manager-rhsm",
                        "dnf-plugin-subscription-manager",
                        "python3-syspurpose",
                        "python3-cloud-what",
                        "json-c.x86_64",
                    )
                ),
            ),
            (
                (8, 0),
                True,
                frozenset(
                    (
                        "subscription-manager",
                        "subscription-manager-rhsm-certificates",
                        "python3-subscription-manager-rhsm",
                        "dnf-plugin-subscription-manager",
                        "python3-syspurpose",
                        "python3-cloud-what",
                        "json-c.x86_64",
                        "json-c.i686",
                    )
                ),
            ),
            (
                (9, 0),
                False,
                frozenset(
                    (
                        "subscription-manager",
                        "subscription-manager-rhsm-certificates",
                        "python3-subscription-manager-rhsm",
                        "python3-cloud-what",
                        "libdnf-plugin-subscription-manager",
                    )
                ),
            ),
        ),
    )
    def test__relevant_subscription_manager_pkgs(
        self, version, json_c_i686_installed, pkgs_to_download, global_system_info, monkeypatch
    ):
        global_system_info.version = Version(*version)
        global_system_info.is_rpm_installed = lambda _: json_c_i686_installed
        monkeypatch.setattr(subscription, "system_info", global_system_info)

        pkgs = subscription._relevant_subscription_manager_pkgs()

        assert pkgs_to_download == frozenset(pkgs)


class TestRestorableSystemSubscription:
    @pytest.fixture
    def system_subscription(self):
        return subscription.RestorableSystemSubscription()

    def test_subscribe_system(self, system_subscription, tool_opts, monkeypatch):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(tool_opts, "username", "user")
        monkeypatch.setattr(tool_opts, "password", "pass")

        system_subscription.enable()

        assert subscription.register_system.call_count == 1

    def test_subscribe_system_already_enabled(self, monkeypatch, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        system_subscription.enabled = True

        system_subscription.enable()

        assert not subscription.register_system.called

    def test_enable_fail_once(self, system_subscription, tool_opts, caplog, monkeypatch):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=1))
        monkeypatch.setattr(tool_opts, "username", "user")
        monkeypatch.setattr(tool_opts, "password", "pass")

        with pytest.raises(exceptions.CriticalError):
            system_subscription.enable()

        assert caplog.records[-1].levelname == "CRITICAL"

    def test_restore(self, monkeypatch, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(subscription, "attach_subscription", mock.Mock(return_value=True))

        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())
        system_subscription.enable()

        system_subscription.restore()

        assert subscription.unregister_system.call_count == 1

    def test_restore_not_enabled(self, monkeypatch, caplog, system_subscription):
        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())

        system_subscription.restore()

        assert not subscription.unregister_system.called

    def test_restore_unregister_call_fails(self, monkeypatch, caplog, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(subscription, "attach_subscription", mock.Mock(return_value=True))

        mocked_unregister_system = UnregisterSystemMocked(side_effect=subscription.UnregisterError("Unregister failed"))
        monkeypatch.setattr(subscription, "unregister_system", mocked_unregister_system)

        system_subscription.enable()

        system_subscription.restore()

        assert mocked_unregister_system.call_count == 1
        assert "Unregister failed" == caplog.records[-1].message

    def test_restore_subman_uninstalled(self, caplog, monkeypatch, system_subscription):
        monkeypatch.setattr(subscription, "register_system", RegisterSystemMocked())
        monkeypatch.setattr(subscription, "attach_subscription", mock.Mock(return_value=True))
        monkeypatch.setattr(
            subscription,
            "unregister_system",
            UnregisterSystemMocked(side_effect=OSError(errno.ENOENT, "command not found")),
        )
        system_subscription.enable()

        system_subscription.restore()

        assert "subscription-manager not installed, skipping" == caplog.messages[-1]


def test_install_rhel_subsription_manager(monkeypatch):
    mock_backup_control = mock.Mock()
    monkeypatch.setattr(backup.backup_control, "push", mock_backup_control)

    subscription.install_rhel_subscription_manager(["subscription-manager", "json-c.x86_64"])

    assert mock_backup_control.push.called_once


@pytest.mark.usefixtures("tool_opts", scope="function")
class TestAttachSubscription:
    def test_attach_subscription_sca_enabled(self, monkeypatch):
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            RunSubprocessMocked(return_string="Content Access Mode is set to Simple Content Access"),
        )
        assert subscription.attach_subscription() is True

    def test_attach_subscription(self, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        assert subscription.attach_subscription() is True

    def test_attach_subscription_available_with_activation_key(self, monkeypatch, caplog):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(toolopts.tool_opts, "activation_key", "dummy_activation_key")
        assert subscription.attach_subscription() is True
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "INFO"

    def test_attach_subscription_fail(self, monkeypatch, caplog):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=1))
        with pytest.raises(exceptions.CriticalError):
            subscription.attach_subscription()
        assert caplog.records[-1].levelname == "CRITICAL"


class TestRegisterSystem:
    @pytest.mark.parametrize(
        ("unregister_system_mock", "stop_rhsm_mock", "expected_log_messages"),
        (
            (UnregisterSystemMocked(), mock.Mock(), []),
            (
                UnregisterSystemMocked(side_effect=subscription.UnregisterError("Unregister failed")),
                mock.Mock(),
                ["Unregister failed"],
            ),
            (
                UnregisterSystemMocked(),
                mock.Mock(side_effect=subscription.StopRhsmError("Stopping RHSM failed")),
                ["Stopping RHSM failed"],
            ),
        ),
    )
    def test_register_system_all_good(
        self,
        tool_opts,
        monkeypatch,
        caplog,
        mocked_rhsm_call_blocking,
        unregister_system_mock,
        stop_rhsm_mock,
        expected_log_messages,
    ):
        monkeypatch.setattr(subscription, "MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE", 1)
        monkeypatch.setattr(subscription, "sleep", mock.Mock())
        monkeypatch.setattr(subscription, "unregister_system", unregister_system_mock)
        monkeypatch.setattr(subscription, "_stop_rhsm", stop_rhsm_mock)

        tool_opts.username = "user"
        tool_opts.password = "pass"

        subscription.register_system()

        assert unregister_system_mock.called
        assert stop_rhsm_mock.called
        assert caplog.records[-1].levelname == "INFO"
        assert caplog.records[-1].message == "System registration succeeded."
        for message in expected_log_messages:
            assert message in caplog.text

    @pytest.mark.rhsm_returns(dbus.exceptions.DBusException("nope"))
    def test_register_system_fail_non_interactive(self, tool_opts, monkeypatch, caplog, mocked_rhsm_call_blocking):
        """Check the critical severity is logged when the credentials are given on the cmdline but registration fails."""
        monkeypatch.setattr(subscription, "MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE", 1)
        monkeypatch.setattr(subscription, "sleep", mock.Mock())
        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())
        monkeypatch.setattr(subscription, "_stop_rhsm", mock.Mock())

        tool_opts.username = "user"
        tool_opts.password = "pass"

        with pytest.raises(exceptions.CriticalError):
            subscription.register_system()

        assert caplog.records[-1].levelname == "CRITICAL"

    @pytest.mark.rhsm_returns((dbus.exceptions.DBusException("nope"), dbus.exceptions.DBusException("nope"), None))
    def test_register_system_fail_interactive(self, tool_opts, monkeypatch, caplog, mocked_rhsm_call_blocking):
        """Test that the three attempts work: fail to register two times and succeed the third time."""
        monkeypatch.setattr(subscription, "sleep", mock.Mock())
        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())
        monkeypatch.setattr(subscription, "_stop_rhsm", mock.Mock())

        fake_from_tool_opts = mock.Mock(
            return_value=subscription.RegistrationCommand(username="invalid", password="invalid")
        )
        monkeypatch.setattr(subscription.RegistrationCommand, "from_tool_opts", fake_from_tool_opts)

        subscription.register_system()

        assert len(mocked_rhsm_call_blocking.call_args_list) == 3
        assert "CRITICAL" not in [rec.levelname for rec in caplog.records]

    @pytest.mark.rhsm_returns((KeyboardInterrupt("bang"),))
    def test_register_system_keyboard_interrupt(self, tool_opts, monkeypatch, caplog, mocked_rhsm_call_blocking):
        """Test that we stop retrying if the user hits Control-C.."""

        monkeypatch.setattr(subscription, "sleep", mock.Mock())
        monkeypatch.setattr(subscription, "unregister_system", UnregisterSystemMocked())
        monkeypatch.setattr(subscription, "_stop_rhsm", mock.Mock())

        pre_created_reg_command = subscription.RegistrationCommand(username="invalid", password="invalid")
        fake_from_tool_opts = mock.Mock(return_value=pre_created_reg_command)
        monkeypatch.setattr(subscription.RegistrationCommand, "from_tool_opts", fake_from_tool_opts)

        with pytest.raises(KeyboardInterrupt):
            subscription.register_system()

        assert len(mocked_rhsm_call_blocking.call_args_list) == 1
        assert "CRITICAL" not in [rec.levelname for rec in caplog.records]

    def test_stop_rhsm(self, caplog, monkeypatch, global_system_info):
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        global_system_info.version = Version(7, 9)
        global_system_info.name = "CentOS Linux"

        run_subprocess_mock = RunSubprocessMocked()
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mock)

        assert subscription._stop_rhsm() is None
        assert caplog.records[-1].message == "RHSM service stopped."

    def test_stop_rhsm_failure(self, caplog, monkeypatch, global_system_info):
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        global_system_info.version = Version(7, 9)

        run_subprocess_mock = RunSubprocessMocked(return_value=("Failure", 1))
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mock)

        with pytest.raises(subscription.StopRhsmError, match="Stopping RHSM failed with code: 1; output: Failure"):
            subscription._stop_rhsm()


class TestRegistrationCommand:
    @pytest.mark.parametrize(
        "registration_kwargs",
        (
            {
                "rhsm_hostname": "localhost",
                "activation_key": "0xDEADBEEF",
                "org": "Local Organization",
            },
            {
                "rhsm_hostname": "localhost",
                "rhsm_port": "8443",
                "rhsm_prefix": "/subscription/",
                "org": "Local Organization",
                "username": "me_myself_and_i",
                "password": "a password",
            },
            {
                "username": "me_myself_and_i",
                "password": "a password",
            },
        ),
    )
    def test_instantiate_via_init(self, registration_kwargs):
        """Test all valid combinations of args to RegistratoinCommand.__init__()."""
        reg_cmd = subscription.RegistrationCommand(**registration_kwargs)
        assert reg_cmd.cmd == "subscription-manager"

        if "server_url" in registration_kwargs:
            assert reg_cmd.server_url == registration_kwargs["server_url"]

        if "activation_key" in registration_kwargs:
            assert reg_cmd.activation_key == registration_kwargs["activation_key"]

        if "org" in registration_kwargs:
            assert reg_cmd.org == registration_kwargs["org"]

        if "password" in registration_kwargs:
            assert reg_cmd.password == registration_kwargs["password"]
            assert reg_cmd.username == registration_kwargs["username"]

        assert reg_cmd.activation_key or reg_cmd.username

    @pytest.mark.parametrize(
        "registration_kwargs, error_message",
        (
            # No credentials specified
            (
                {
                    "rhsm_hostname": "localhost",
                    "org": "Local Organization",
                },
                "activation_key and org or username and password must be specified",
            ),
            # Activation key without an org
            (
                {
                    "rhsm_hostname": "localhost",
                    "activation_key": "0xDEADBEEF",
                },
                "org must be specified if activation_key is used",
            ),
            # Username without a password
            (
                {
                    "rhsm_hostname": "localhost",
                    "username": "me_myself_and_i",
                },
                "username and password must be used together",
            ),
            # Password without a username
            (
                {
                    "rhsm_hostname": "localhost",
                    "password": "a password",
                },
                "username and password must be used together",
            ),
        ),
    )
    def test_instantiate_failures(self, registration_kwargs, error_message):
        """Test various failures instantiating RegistrationCommand."""
        with pytest.raises(ValueError, match=error_message):
            subscription.RegistrationCommand(**registration_kwargs)

    @pytest.mark.parametrize(
        "registration_kwargs",
        (
            {
                "rhsm_hostname": "localhost",
                "activation_key": "0xDEADBEEF",
                "org": "Local Organization",
            },
            {
                "rhsm_hostname": "localhost",
                "rhsm_port": "8800",
                "rhsm_prefix": "/rhsm",
                "org": "Local Organization",
                "username": "me_myself_and_i",
                "password": "a password",
            },
            {
                "username": "me_myself_and_i",
                "password": "a password",
            },
        ),
    )
    def test_from_tool_opts_all_data_on_cli(self, registration_kwargs, tool_opts):
        """Test that the RegistrationCommand is created from toolopts successfully."""
        for tool_opt_name, value in registration_kwargs.items():
            setattr(tool_opts, tool_opt_name, value)

        reg_cmd = subscription.RegistrationCommand.from_tool_opts(tool_opts)

        assert reg_cmd.cmd == "subscription-manager"

        if "rhsm_hostname" in registration_kwargs:
            assert reg_cmd.rhsm_hostname == registration_kwargs["rhsm_hostname"]

        if "rhsm_port" in registration_kwargs:
            assert reg_cmd.rhsm_port == registration_kwargs["rhsm_port"]

        if "rhsm_prefix" in registration_kwargs:
            assert reg_cmd.rhsm_prefix == registration_kwargs["rhsm_prefix"]

        if "org" in registration_kwargs:
            assert reg_cmd.org == registration_kwargs["org"]

        if "activation_key" in registration_kwargs:
            assert reg_cmd.activation_key == registration_kwargs["activation_key"]

        if "username" in registration_kwargs:
            assert reg_cmd.username == registration_kwargs["username"]

        if "password" in registration_kwargs:
            assert reg_cmd.password == registration_kwargs["password"]

    @pytest.mark.parametrize(
        "registration_kwargs, prompt_input",
        (
            # no activation_key no password
            (
                {"username": "me_myself_and_i"},
                {"Password: ": "a password"},
            ),
            # no activation_key no username
            (
                {"password": "a password"},
                {"Username: ": "me_myself_and_i"},
            ),
            # no credentials at all
            (
                {},
                {"Username: ": "me_myself_and_i", "Password: ": "a password"},
            ),
        ),
    )
    def test_from_tool_opts_interactive_data(self, registration_kwargs, prompt_input, tool_opts, monkeypatch):
        """Test that things work when we interactively ask for more data."""

        def prompt_user(prompt, password=False):
            if prompt in prompt_input:
                return prompt_input[prompt]
            raise Exception("Should not have been called with that prompt for the input")

        monkeypatch.setattr(utils, "prompt_user", PromptUserMocked(side_effect=prompt_user))

        for option_name, option_value in registration_kwargs.items():
            setattr(tool_opts, option_name, option_value)

        registration_cmd = subscription.RegistrationCommand.from_tool_opts(tool_opts)

        if "Password: " in prompt_input:
            assert registration_cmd.password == prompt_input["Password: "]

        if "Username: " in prompt_input:
            assert registration_cmd.username == prompt_input["Username: "]

        # assert that we prompted the user the number of times that we expected
        assert utils.prompt_user.call_count == len(prompt_input)

    def test_from_tool_opts_username_empty_string(self, tool_opts, monkeypatch):
        monkeypatch.setattr(utils, "prompt_user", PromptUserMocked(retries=1))

        registration_cmd = subscription.RegistrationCommand.from_tool_opts(tool_opts)

        assert registration_cmd.username == "test"
        assert registration_cmd.password == "test"
        assert utils.prompt_user.prompts == {"Username: ": 2, "Password: ": 2}

    @pytest.mark.parametrize(
        ("rhsm_hostname", "rhsm_port", "rhsm_prefix", "expected"),
        (
            (None, None, None, dbus.Dictionary({}, signature="ss")),
            ("localhost", None, None, dbus.Dictionary({"host": "localhost"}, signature="ss")),
            ("localhost", "8443", None, dbus.Dictionary({"host": "localhost", "port": "8443"}, signature="ss")),
            (
                "localhost",
                "8443",
                "subscription",
                dbus.Dictionary({"host": "localhost", "port": "8443", "handler": "subscription"}, signature="ss"),
            ),
            (
                "localhost",
                None,
                "/subscription",
                dbus.Dictionary({"host": "localhost", "handler": "/subscription"}, signature="ss"),
            ),
        ),
    )
    def test_connection_opts(self, rhsm_hostname, rhsm_port, rhsm_prefix, expected):
        reg_cmd = subscription.RegistrationCommand(
            org="justice_league",
            activation_key="wonder twin powers",
            rhsm_hostname=rhsm_hostname,
            rhsm_port=rhsm_port,
            rhsm_prefix=rhsm_prefix,
        )
        assert reg_cmd.connection_opts == expected

    @pytest.mark.parametrize(
        (
            "organization",
            "activation_key",
            "username",
            "password",
            "register_var",
            "register_signature",
            "organization_log",
        ),
        (
            (
                "Local Organization",
                "0xDEADBEEF",
                None,
                None,
                "RegisterWithActivationKeys",
                "sasa{sv}a{sv}s",
                "Organization: *****",
            ),
            (
                "Local Organization",
                None,
                "user_name",
                "pass_word",
                "Register",
                "sssa{sv}a{sv}s",
                "Organization: *****",
            ),
            (None, None, "user_name", "pass_word", "Register", "sssa{sv}a{sv}s", None),
        ),
    )
    def test_calling_registration_command(
        self,
        organization,
        activation_key,
        username,
        password,
        register_var,
        register_signature,
        organization_log,
        monkeypatch,
        mocked_rhsm_call_blocking,
        caplog,
    ):
        reg_cmd = subscription.RegistrationCommand(
            username=username, password=password, org=organization, activation_key=activation_key
        )

        reg_cmd()
        if password:
            args = (
                organization or "",
                username,
                password,
                {},
                {},
                "C",
            )

        else:
            args = (
                organization or "",
                [activation_key],
                {},
                {},
                "C",
            )

        mocked_rhsm_call_blocking.assert_called_once_with(
            "com.redhat.RHSM1",
            "/com/redhat/RHSM1/Register",
            "com.redhat.RHSM1.Register",
            register_var,
            register_signature,
            args,
            timeout=subscription.REGISTRATION_TIMEOUT,
        )

        if organization_log is None:
            assert "Organization: " not in caplog.text
        else:
            assert organization_log in caplog.text

    def test_calling_registration_command_with_connection_opts(self, monkeypatch, mocked_rhsm_call_blocking):
        reg_cmd = subscription.RegistrationCommand(
            username="me_myself_and_i",
            password="a password",
            rhsm_hostname="rhsm.redhat.com",
            rhsm_port="443",
            rhsm_prefix="/",
        )

        run_subprocess_mocked = RunSubprocessMocked()
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

        reg_cmd()

        assert run_subprocess_mocked.call_count == 1
        call_args = tuple(run_subprocess_mocked.call_args)
        assert call_args[0][0][:2] == ["subscription-manager", "config"]
        assert len(run_subprocess_mocked.call_args[0][0][2:]) == 3
        assert "--server.hostname=rhsm.redhat.com" in call_args[0][0][2:]
        assert "--server.port=443" in call_args[0][0][2:]
        assert "--server.prefix=/" in call_args[0][0][2:]

    def test_calling_registration_command_with_serverurl_fails_setting_config(
        self, monkeypatch, mocked_rhsm_call_blocking
    ):
        reg_cmd = subscription.RegistrationCommand(
            username="me_myself_and_i", password="a password", rhsm_hostname="https://rhsm.redhat.com"
        )

        run_subprocess_mocked = RunSubprocessMocked(return_value=("failed to set server.hostname", 1))
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

        with pytest.raises(
            ValueError,
            match="Error setting the subscription-manager connection configuration: failed to set server.hostname",
        ):
            reg_cmd()

        run_subprocess_mocked.assert_called_once_with(
            ["subscription-manager", "config", "--server.hostname=https://rhsm.redhat.com"], print_cmd=mock.ANY
        )

    @pytest.mark.rhsm_returns((dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.NoReply"),))
    def test_registration_succeeds_but_dbus_returns_noreply(self, monkeypatch, mocked_rhsm_call_blocking):
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            RunSubprocessMocked(
                return_string=(
                    "system identity: 1234-56-78-9abc\n" "name: abc-123\n" "org name: Test\n" "org ID: 12345678910\n"
                )
            ),
        )

        reg_cmd = subscription.RegistrationCommand(
            username="me_myself_and_i",
            password="a password",
        )

        assert reg_cmd() is None

    @pytest.mark.rhsm_returns((dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.NoReply"),))
    def test_registration_fails_and_dbus_returns_noreply(self, caplog, monkeypatch, mocked_rhsm_call_blocking):
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            RunSubprocessMocked(
                return_value=(
                    "This system is not yet registered."
                    " Try 'subscription-manager register"
                    " --help' for more information.\n",
                    1,
                )
            ),
        )

        reg_cmd = subscription.RegistrationCommand(
            username="me_myself_and_i",
            password="a password",
        )

        with pytest.raises(dbus.exceptions.DBusException):
            reg_cmd()


class TestUnregisteringSystem:
    @pytest.mark.parametrize(
        ("output", "ret_code", "expected"),
        (("", 0, "System unregistered successfully."),),
    )
    def test_unregister_system(self, output, ret_code, expected, monkeypatch, caplog):
        submgr_command = ("subscription-manager", "unregister")
        rpm_command = ("rpm", "--quiet", "-q", "subscription-manager")

        # Mock rpm command
        run_subprocess_mock = RunSubprocessMocked(
            side_effect=run_subprocess_side_effect(
                (
                    submgr_command,
                    (
                        output,
                        ret_code,
                    ),
                ),
                (rpm_command, ("", 0)),
            ),
        )
        monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess_mock)

        subscription.unregister_system()

        assert expected in caplog.records[-1].message

    @pytest.mark.parametrize(
        ("output", "ret_code", "expected"),
        (("Failed to unregister.", 1, "System unregistration failed"),),
    )
    def test_unregister_system_failure(self, output, ret_code, expected, monkeypatch, caplog):
        submgr_command = ("subscription-manager", "unregister")
        rpm_command = ("rpm", "--quiet", "-q", "subscription-manager")

        # Mock rpm command
        run_subprocess_mock = RunSubprocessMocked(
            side_effect=run_subprocess_side_effect(
                (
                    submgr_command,
                    (
                        output,
                        ret_code,
                    ),
                ),
                (rpm_command, ("", 0)),
            ),
        )
        monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess_mock)

        with pytest.raises(
            subscription.UnregisterError,
            match="System unregistration result:\n%s" % output,
        ):
            subscription.unregister_system()

    def test_unregister_system_submgr_not_found(self, monkeypatch, caplog):
        rpm_command = ["rpm", "--quiet", "-q", "subscription-manager"]

        run_subprocess_mock = RunSubprocessMocked(
            side_effect=unit_tests.run_subprocess_side_effect(
                (rpm_command, ("", 1)),
            )
        )
        monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess_mock)
        subscription.unregister_system()
        assert "The subscription-manager package is not installed." in caplog.records[-1].message


class TestVerifyRhsmInstalled:
    def test_verify_rhsm_installed_success(self, monkeypatch, caplog):
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_information",
            lambda _: [create_pkg_information(name="subscription-manager")],
        )

        subscription.verify_rhsm_installed()

        assert "subscription-manager installed correctly." in caplog.text

    def test_verify_rhsm_installed_failure(self, monkeypatch, caplog):
        monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda _: None)

        with pytest.raises(exceptions.CriticalError):
            subscription.verify_rhsm_installed()

        assert "The subscription-manager package is not installed correctly." in caplog.text


# ----


def test_get_pool_id():
    SUBSCRIPTION_DETAILS = (
        "Subscription Name: Good subscription\n"
        "Provides:          Something good\n"
        "SKU:               00EEE00EE\n"
        "Contract:          01234567\n"
        "Pool ID:           8aaaa123045897fb564240aa00aa0000\n"
        "Available:         1\n"
        "Suggested:         1\n"
        "Service Level:     Self-icko\n"
        "Service Type:      L1-L3\n"
        "Subscription Type: Standard\n"
        "Ends:              2018/26/07\n"
        "System Type:       Virtual\n\n"  # this has changed to Entitlement Type since RHEL 7.8
    )

    # Check that we can distill the pool id from the subscription description
    pool_id = subscription.get_pool_id(SUBSCRIPTION_DETAILS)

    assert pool_id == "8aaaa123045897fb564240aa00aa0000"


@pytest.mark.parametrize(
    ("rhel_repoids", "subprocess", "should_raise", "expected", "expected_message"),
    (
        (
            ["repo-1", "repo-2"],
            ("repo-1, repo-2", 0),
            False,
            ["repo-1", "repo-2"],
            "Repositories enabled through subscription-manager",
        ),
        (
            ["repo-1", "repo-2"],
            ("repo-1, repo-2", 1),
            True,
            ["repo-1", "repo-2"],
            "Repositories were not possible to enable through subscription-manager:\nrepo-1, repo-2",
        ),
        (
            ["rhel-8-for-x86_64-baseos-eus-rpms", "rhel-8-for-x86_64-appstream-eus-rpms"],
            ("repo-1, repo-2", 0),
            False,
            ["rhel-8-for-x86_64-baseos-eus-rpms", "rhel-8-for-x86_64-appstream-eus-rpms"],
            "Repositories enabled through subscription-manager",
        ),
    ),
)
@centos8
def test_enable_repos_rhel_repoids(
    pretend_os, rhel_repoids, subprocess, should_raise, expected, expected_message, monkeypatch, caplog
):
    cmd_mock = ["subscription-manager", "repos"]
    for repo in rhel_repoids:
        cmd_mock.append("--enable=%s" % repo)

    run_subprocess_mock = RunSubprocessMocked(
        side_effect=unit_tests.run_subprocess_side_effect(
            (cmd_mock, subprocess),
        )
    )
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    if should_raise:
        with pytest.raises(SystemExit):
            subscription.enable_repos(rhel_repoids=rhel_repoids)
    else:
        subscription.enable_repos(rhel_repoids=rhel_repoids)
        assert system_info.submgr_enabled_repos == expected

    assert expected_message in caplog.records[-1].message
    assert run_subprocess_mock.call_count == 1


@pytest.mark.parametrize(
    ("rhel_repoids", "default_rhsm_repoids", "subprocess", "subprocess2", "should_raise", "expected"),
    (
        (
            ["rhel-8-for-x86_64-baseos-eus-rpms", "rhel-8-for-x86_64-appstream-eus-rpms"],
            ["test-repo-1", "test-repo-2"],
            ("rhel-8-for-x86_64-baseos-eus-rpms, rhel-8-for-x86_64-appstream-eus-rpms", 1),
            ("test-repo-1, test-repo-2", 1),
            True,
            "Repositories were not possible to enable through subscription-manager:\ntest-repo-1, test-repo-2",
        ),
        (
            ["rhel-8-for-x86_64-baseos-eus-rpms", "rhel-8-for-x86_64-appstream-eus-rpms"],
            ["test-repo-1", "test-repo-2"],
            ("rhel-8-for-x86_64-baseos-eus-rpms, rhel-8-for-x86_64-appstream-eus-rpms", 1),
            ("test-repo-1, test-repo-2", 0),
            False,
            "Repositories enabled through subscription-manager",
        ),
    ),
)
@centos8
def test_enable_repos_rhel_repoids_fallback_default_rhsm(
    pretend_os,
    rhel_repoids,
    default_rhsm_repoids,
    subprocess,
    subprocess2,
    should_raise,
    expected,
    monkeypatch,
    caplog,
):
    cmd_mock = ["subscription-manager", "repos"]
    for repo in rhel_repoids:
        cmd_mock.append("--enable=%s" % repo)

    run_subprocess_mock = RunSubprocessMocked(side_effect=[subprocess, subprocess2])
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(system_info, "default_rhsm_repoids", value=default_rhsm_repoids)

    if should_raise:
        with pytest.raises(SystemExit):
            subscription.enable_repos(rhel_repoids=rhel_repoids)
    else:
        subscription.enable_repos(rhel_repoids=rhel_repoids)
        assert system_info.submgr_enabled_repos == default_rhsm_repoids

    assert expected in caplog.records[-1].message
    assert run_subprocess_mock.call_count == 2


@pytest.mark.parametrize(
    ("toolopts_enablerepo", "subprocess", "should_raise", "expected", "expected_message"),
    (
        (
            ["repo-1", "repo-2"],
            ("repo-1, repo-2", 0),
            False,
            ["repo-1", "repo-2"],
            "Repositories enabled through subscription-manager",
        ),
        (
            ["repo-1", "repo-2"],
            ("repo-1, repo-2", 1),
            True,
            ["repo-1", "repo-2"],
            "Repositories were not possible to enable through subscription-manager:\nrepo-1, repo-2",
        ),
        (
            ["rhel-8-for-x86_64-baseos-eus-rpms", "rhel-8-for-x86_64-appstream-eus-rpms"],
            ("repo-1, repo-2", 0),
            False,
            ["rhel-8-for-x86_64-baseos-eus-rpms", "rhel-8-for-x86_64-appstream-eus-rpms"],
            "Repositories enabled through subscription-manager",
        ),
    ),
)
def test_enable_repos_toolopts_enablerepo(
    toolopts_enablerepo,
    subprocess,
    should_raise,
    expected,
    expected_message,
    tool_opts,
    monkeypatch,
    caplog,
):
    cmd_mock = ["subscription-manager", "repos"]
    for repo in toolopts_enablerepo:
        cmd_mock.append("--enable=%s" % repo)

    run_subprocess_mock = RunSubprocessMocked(
        side_effect=unit_tests.run_subprocess_side_effect(
            (cmd_mock, subprocess),
        )
    )
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    tool_opts.enablerepo = toolopts_enablerepo
    # monkeypatch.setattr(tool_opts, "enablerepo", toolopts_enablerepo)

    if should_raise:
        with pytest.raises(SystemExit):
            subscription.enable_repos(rhel_repoids=None)
    else:
        subscription.enable_repos(rhel_repoids=None)
        assert system_info.submgr_enabled_repos == expected

    assert expected_message in caplog.records[-1].message
    assert run_subprocess_mock.call_count == 1


@pytest.mark.parametrize(
    ("subprocess", "expected"),
    (
        (("output", 0), "RHEL repositories locked"),
        (("output", 1), "Locking RHEL repositories failed"),
    ),
)
@centos8
def test_lock_releasever_in_rhel_repositories(subprocess, expected, monkeypatch, caplog, pretend_os):
    cmd = ["subscription-manager", "release", "--set=%s" % system_info.releasever]
    run_subprocess_mock = RunSubprocessMocked(
        side_effect=unit_tests.run_subprocess_side_effect(
            (cmd, subprocess),
        )
    )
    version = Version(8, 6)
    monkeypatch.setattr(system_info, "version", version)
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(system_info, "eus_system", value=True)
    subscription.lock_releasever_in_rhel_repositories()

    assert expected in caplog.records[-1].message
    assert run_subprocess_mock.call_count == 1


@centos7
def test_lock_releasever_in_rhel_repositories_not_eus(pretend_os, caplog):
    subscription.lock_releasever_in_rhel_repositories()
    assert "Skipping locking RHEL repositories to a specific EUS minor version." in caplog.records[-1].message


@pytest.mark.parametrize(
    ("subprocess", "expected"),
    (
        (("output", 0), "RHSM custom facts uploaded successfully."),
        (("output", 1), "Failed to update the RHSM custom facts with return code '1' and output 'output'."),
    ),
)
@centos7
def test_update_rhsm_custom_facts(subprocess, expected, pretend_os, monkeypatch, caplog):
    cmd = ["subscription-manager", "facts", "--update"]
    run_subprocess_mock = RunSubprocessMocked(
        side_effect=unit_tests.run_subprocess_side_effect(
            (cmd, subprocess),
        ),
    )
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    subscription.update_rhsm_custom_facts()
    assert expected in caplog.records[-1].message


def test_update_rhsm_custom_facts_no_rhsm(global_tool_opts, caplog, monkeypatch):
    monkeypatch.setattr(subscription, "tool_opts", global_tool_opts)
    global_tool_opts.no_rhsm = True

    subscription.update_rhsm_custom_facts()
    assert "Skipping updating RHSM custom facts." in caplog.records[-1].message


def test_update_rhsm_custom_facts_disable_telemetry(monkeypatch, caplog):
    message = "Telemetry disabled, skipping RHSM facts upload."
    monkeypatch.setenv("CONVERT2RHEL_DISABLE_TELEMETRY", "1")

    subscription.update_rhsm_custom_facts()

    assert message in caplog.records[-1].message
