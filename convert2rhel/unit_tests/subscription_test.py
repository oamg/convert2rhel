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

import logging
import os
import unittest

from collections import namedtuple

import dbus
import dbus.connection
import dbus.exceptions
import pexpect
import pytest
import six

from six.moves import urllib

from convert2rhel import backup, pkghandler, subscription, toolopts, unit_tests, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import GetLoggerMocked, get_pytest_marker, run_subprocess_side_effect
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


class DumbCallable(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0

    def __call__(self, *args, **kwargs):
        self.called += 1


class RunSubprocessMocked(unit_tests.MockFunction):
    def __init__(self, tuples=None):
        # you can specify sequence of return (object, return code) as
        # a list of tuple that will be consumed continuosly on the each
        # call; when the list is consumed or it is empty, the default
        # tuple is returned
        self.tuples = tuples
        self.default_tuple = ("output", 0)
        self.called = 0
        self.cmd = []

    def __call__(self, cmd, *args, **kwargs):
        self.cmd = cmd
        self.called += 1

        if self.tuples:
            return self.tuples.pop(0)
        return self.default_tuple


class PromptUserLoopMocked(unit_tests.MockFunction):
    def __init__(self):
        self.called = {}

    def __call__(self, *args, **kwargs):
        return_value = ""

        # args[0] is the current question being asked
        if args[0] not in self.called:
            self.called[args[0]] = 0

        if self.called[args[0]] >= 1:
            return_value = "test"

        self.called[args[0]] += 1
        return return_value


class LetUserChooseItemMocked(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0

    def __call__(self, *args, **kwargs):
        self.called += 1
        return 0


class GetOneSubMocked(unit_tests.MockFunction):
    def __call__(self, *args, **kwargs):
        Sub = namedtuple("Sub", ["pool_id", "sub_raw"])

        subscription1 = Sub("samplepool", "Subscription description")
        return [subscription1]


class GetAvailSubsMocked(unit_tests.MockFunction):
    def __call__(self, *args, **kwargs):
        Sub = namedtuple("Sub", ["pool_id", "sub_raw"])

        subscription1 = Sub("samplepool", "Subscription description")
        subscription2 = Sub("pool0", "sub desc")
        return [subscription1, subscription2]


class GetNoAvailSubsMocked(unit_tests.MockFunction):
    def __call__(self, *args, **kwargs):
        return []


class GetNoAvailSubsOnceMocked(unit_tests.MockFunction):
    def __init__(self):
        self.empty_last_call = False

    def __call__(self, *args, **kwargs):
        if not self.empty_last_call:
            self.empty_last_call = True
            return []

        self.empty_last_call = False
        return [namedtuple("Sub", ["pool_id", "sub_raw"])("samplepool", "Subscription description")]


class TestSubscription(unittest.TestCase):
    class IsFileMocked(unit_tests.MockFunction):
        def __init__(self, is_file):
            self.is_file = is_file

        def __call__(self, *args, **kwargs):
            return self.is_file

    class PromptUserMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return True

    class RemoveFileMocked(unit_tests.MockFunction):
        def __init__(self, removed=True):
            self.removed = removed

        def __call__(self, *args, **kwargs):
            return self.removed

    class CallYumCmdMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.return_code = 0
            self.return_string = "Test output"
            self.fail_once = False
            self.command = None
            self.args = None

        def __call__(self, command, args):
            if self.fail_once and self.called == 0:
                self.return_code = 1
            if self.fail_once and self.called > 0:
                self.return_code = 0
            self.called += 1
            self.command = command
            self.args = args
            return self.return_string, self.return_code

    ##########################################################################

    def setUp(self):
        tool_opts.__init__()

    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    def test_get_pool_id(self):
        # Check that we can distill the pool id from the subscription description
        pool_id = subscription.get_pool_id(self.SUBSCRIPTION_DETAILS)

        self.assertEqual(pool_id, "8aaaa123045897fb564240aa00aa0000")

    # Details of one subscription as output by `subscription-manager list --available`
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

    class LogMocked(unit_tests.MockFunction):
        def __init__(self):
            self.msg = ""

        def __call__(self, msg):
            self.msg += "%s\n" % msg

    @unit_tests.mock(logging.Logger, "info", LogMocked())
    @unit_tests.mock(logging.Logger, "warning", LogMocked())
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(subscription, "get_avail_repos", lambda: ["rhel_x", "rhel_y"])
    def test_check_needed_repos_availability(self):
        subscription.check_needed_repos_availability(["rhel_x"])
        self.assertTrue("Needed RHEL repositories are available." in logging.Logger.info.msg)

        subscription.check_needed_repos_availability(["rhel_z"])
        self.assertTrue("rhel_z repository is not available" in logging.Logger.warning.msg)

    @unit_tests.mock(logging.Logger, "warning", LogMocked())
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(subscription, "get_avail_repos", lambda: [])
    def test_check_needed_repos_availability_no_repo_available(self):
        subscription.check_needed_repos_availability(["rhel"])
        self.assertTrue("rhel repository is not available" in logging.Logger.warning.msg)

    @unit_tests.mock(pkghandler, "get_installed_pkg_objects", lambda _: [namedtuple("Pkg", ["name"])("submgr")])
    @unit_tests.mock(pkghandler, "print_pkg_info", lambda x: None)
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(backup, "remove_pkgs", DumbCallable())
    def test_remove_original_subscription_manager(self):
        subscription.remove_original_subscription_manager()

        self.assertEqual(backup.remove_pkgs.called, 1)

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkg_objects",
        lambda _: [namedtuple("Pkg", ["name"])("subscription-manager-initial-setup-addon")],
    )
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(8, 5))
    @unit_tests.mock(system_info, "id", "centos")
    @unit_tests.mock(pkghandler, "print_pkg_info", lambda x: None)
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(backup, "remove_pkgs", DumbCallable())
    def test_remove_original_subscription_manager_missing_package_ol_85(self):
        subscription.remove_original_subscription_manager()
        self.assertEqual(backup.remove_pkgs.called, 2)

    @unit_tests.mock(pkghandler, "get_installed_pkg_objects", lambda _: [])
    @unit_tests.mock(subscription, "loggerinst", GetLoggerMocked())
    def test_remove_original_subscription_manager_no_pkgs(self):
        subscription.remove_original_subscription_manager()

        self.assertEqual(len(subscription.loggerinst.info_msgs), 2)
        self.assertTrue(
            "No packages related to subscription-manager installed." in subscription.loggerinst.info_msgs[-1]
        )

    @unit_tests.mock(logging.Logger, "info", LogMocked())
    @unit_tests.mock(os.path, "isdir", lambda x: True)
    @unit_tests.mock(os, "listdir", lambda x: ["filename"])
    @unit_tests.mock(
        pkghandler,
        "call_yum_cmd",
        lambda command, args, print_output, enable_repos, disable_repos, set_releasever: (None, 0),
    )
    @unit_tests.mock(pkghandler, "filter_installed_pkgs", DumbCallable())
    @unit_tests.mock(pkghandler, "get_pkg_names_from_rpm_paths", DumbCallable())
    @unit_tests.mock(backup.changed_pkgs_control, "track_installed_pkgs", DumbCallable())
    @unit_tests.mock(subscription, "track_installed_submgr_pkgs", DumbCallable())
    def test_install_rhel_subscription_manager(self):
        subscription.install_rhel_subscription_manager()
        self.assertEqual(pkghandler.get_pkg_names_from_rpm_paths.called, 1)
        self.assertTrue("\nPackages installed:\n" in logging.Logger.info.msg)
        self.assertEqual(subscription.track_installed_submgr_pkgs.called, 1)

    @unit_tests.mock(logging.Logger, "warning", LogMocked())
    @unit_tests.mock(os.path, "isdir", lambda x: True)
    @unit_tests.mock(os, "listdir", lambda x: "")
    @unit_tests.mock(subscription, "SUBMGR_RPMS_DIR", "")
    def test_install_rhel_subscription_manager_without_packages(self):
        subscription.install_rhel_subscription_manager()
        self.assertTrue("No RPMs found" in logging.Logger.warning.msg)

    @unit_tests.mock(os, "listdir", lambda x: [":w"])
    @unit_tests.mock(
        pkghandler,
        "call_yum_cmd",
        lambda command, args, print_output, enable_repos, disable_repos, set_releasever: (None, 1),
    )
    @unit_tests.mock(pkghandler, "filter_installed_pkgs", lambda x: ["test"])
    @unit_tests.mock(pkghandler, "get_pkg_names_from_rpm_paths", lambda x: ["test"])
    def test_install_rhel_subscription_manager_unable_to_install(self):
        self.assertRaises(SystemExit, subscription.install_rhel_subscription_manager)

    class StoreContentMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.filename = None
            self.content = None

        def __call__(self, filename, content):
            self.called += 1
            self.filename = filename
            self.content = content
            return True

    class DownloadPkgsMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.to_return = ["/path/to.rpm"]

        def __call__(self, pkgs, dest, reposdir=None):
            self.called += 1
            self.pkgs = pkgs
            self.dest = dest
            self.reposdir = reposdir
            return self.to_return

    @unit_tests.mock(utils, "store_content_to_file", StoreContentMocked())
    @unit_tests.mock(utils, "download_pkgs", DownloadPkgsMocked())
    def test__download_rhsm_pkgs(self):
        subscription._download_rhsm_pkgs(["testpkg"], "/path/to.repo", "content")

        self.assertTrue("/path/to.repo" in utils.store_content_to_file.filename)
        self.assertEqual(utils.download_pkgs.called, 1)

        utils.download_pkgs.to_return.append(None)

        self.assertRaises(SystemExit, subscription._download_rhsm_pkgs, ["testpkg"], "/path/to.repo", "content")

    class DownloadPkgMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.to_return = "/path/to.rpm"

        def __call__(self, pkg, dest, reposdir=None):
            self.called += 1
            self.pkg = pkg
            self.dest = dest
            self.reposdir = reposdir
            return self.to_return


@pytest.fixture
def tool_opts(global_tool_opts, monkeypatch):
    monkeypatch.setattr(subscription, "tool_opts", global_tool_opts)
    return global_tool_opts


class TestSubscribeSystem(object):
    def test_subscribe_system(self, tool_opts, monkeypatch):
        monkeypatch.setattr(subscription, "register_system", DumbCallable())
        monkeypatch.setattr(subscription, "get_avail_subs", GetAvailSubsMocked())
        monkeypatch.setattr(utils, "let_user_choose_item", LetUserChooseItemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        tool_opts.username = "user"
        tool_opts.password = "pass"

        subscription.subscribe_system()

        assert subscription.register_system.called == 1

    def test_subscribe_system_fail_once(self, tool_opts, monkeypatch):
        monkeypatch.setattr(subscription, "register_system", DumbCallable())
        monkeypatch.setattr(subscription, "get_avail_subs", GetNoAvailSubsOnceMocked())
        monkeypatch.setattr(utils, "let_user_choose_item", LetUserChooseItemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        tool_opts.username = "user"
        tool_opts.password = "pass"

        subscription.subscribe_system()

        assert subscription.register_system.called == 2


@pytest.mark.usefixtures("tool_opts", scope="function")
class TestAttachSubscription(object):
    def test_attach_subscription_one_sub_available(self, monkeypatch):
        monkeypatch.setattr(subscription, "get_avail_subs", GetOneSubMocked())
        monkeypatch.setattr(utils, "let_user_choose_item", LetUserChooseItemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        assert subscription.attach_subscription() is True
        assert utils.let_user_choose_item.called == 0

    def test_attach_subscription_multiple_subs_available(self, monkeypatch):
        monkeypatch.setattr(subscription, "get_avail_subs", GetAvailSubsMocked())
        monkeypatch.setattr(utils, "let_user_choose_item", LetUserChooseItemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        assert subscription.attach_subscription() is True
        assert utils.let_user_choose_item.called == 1

    def test_attach_subscription_available_with_activation_key(self, monkeypatch, caplog):
        monkeypatch.setattr(subscription, "get_avail_subs", GetAvailSubsMocked())
        monkeypatch.setattr(utils, "let_user_choose_item", LetUserChooseItemMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(toolopts.tool_opts, "activation_key", "dummy_activation_key")

        assert subscription.attach_subscription() is True
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "INFO"

    def test_attach_subscription_none_available(self, monkeypatch):
        monkeypatch.setattr(subscription, "get_avail_subs", GetNoAvailSubsMocked())

        assert subscription.attach_subscription() is False


class TestRegisterSystem(object):
    @pytest.mark.parametrize(
        ("unregister_system_mock", "stop_rhsm_mock", "expected_log_messages"),
        (
            (mock.Mock(), mock.Mock(), []),
            (
                mock.Mock(side_effect=subscription.UnregisterError("Unregister failed")),
                mock.Mock(),
                ["Unregister failed"],
            ),
            (
                mock.Mock(),
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
        tool_opts.credentials_thru_cli = True

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
        monkeypatch.setattr(subscription, "unregister_system", mock.Mock())
        monkeypatch.setattr(subscription, "_stop_rhsm", mock.Mock())

        tool_opts.username = "user"
        tool_opts.password = "pass"
        tool_opts.credentials_thru_cli = True

        with pytest.raises(SystemExit):
            subscription.register_system()

        assert caplog.records[-1].levelname == "CRITICAL"

    @pytest.mark.rhsm_returns((dbus.exceptions.DBusException("nope"), dbus.exceptions.DBusException("nope"), None))
    def test_register_system_fail_interactive(self, tool_opts, monkeypatch, caplog, mocked_rhsm_call_blocking):
        """Test that the three attempts work: fail to register two times and succeed the third time."""
        tool_opts.credentials_thru_cli = False
        monkeypatch.setattr(subscription, "sleep", mock.Mock())
        monkeypatch.setattr(subscription, "unregister_system", mock.Mock())
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

        tool_opts.credentials_thru_cli = False
        monkeypatch.setattr(subscription, "sleep", mock.Mock())
        monkeypatch.setattr(subscription, "unregister_system", mock.Mock())
        monkeypatch.setattr(subscription, "_stop_rhsm", mock.Mock())

        pre_created_reg_command = subscription.RegistrationCommand(username="invalid", password="invalid")
        fake_from_tool_opts = mock.Mock(return_value=pre_created_reg_command)
        monkeypatch.setattr(subscription.RegistrationCommand, "from_tool_opts", fake_from_tool_opts)

        with pytest.raises(KeyboardInterrupt):
            subscription.register_system()

        assert len(mocked_rhsm_call_blocking.call_args_list) == 1
        assert "CRITICAL" not in [rec.levelname for rec in caplog.records]

    @pytest.mark.parametrize(
        ("rhel_major_version", "expected_message"),
        (
            (6, "Skipping RHSM service shutdown on CentOS Linux 6."),
            (7, "RHSM service stopped."),
        ),
    )
    def test_stop_rhsm(self, caplog, monkeypatch, global_system_info, rhel_major_version, expected_message):
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        global_system_info.version = Version(rhel_major_version, 10)
        global_system_info.name = "CentOS Linux"

        run_subprocess_mock = mock.Mock(return_value=("Success", 0))
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mock)

        assert subscription._stop_rhsm() is None
        assert caplog.records[-1].message == expected_message

    @pytest.mark.parametrize(
        "rhel_major_version",
        (
            # 6 currently doesn't stop rhsm-service.  Revisit if we get host
            # already registered errors
            # 6,
            7,
        ),
    )
    def test_stop_rhsm_failure(self, caplog, monkeypatch, global_system_info, rhel_major_version):
        monkeypatch.setattr(subscription, "system_info", global_system_info)
        global_system_info.version = Version(rhel_major_version, 10)

        run_subprocess_mock = mock.Mock(return_value=("Failure", 1))
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mock)

        with pytest.raises(subscription.StopRhsmError, match="Stopping RHSM failed with code: 1; output: Failure"):
            subscription._stop_rhsm()


class TestRegistrationCommand(object):
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
            cmd = subscription.RegistrationCommand(**registration_kwargs)

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
            # activation_key and not org
            (
                {"activation_key": "0xDEADBEEF"},
                {"Organization: ": "Local Organization"},
            ),
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

        fake_prompt_user = mock.Mock(side_effect=prompt_user)

        monkeypatch.setattr(utils, "prompt_user", fake_prompt_user)

        for option_name, option_value in registration_kwargs.items():
            setattr(tool_opts, option_name, option_value)

        registration_cmd = subscription.RegistrationCommand.from_tool_opts(tool_opts)

        if "Organization: " in prompt_input:
            assert registration_cmd.org == prompt_input["Organization: "]

        if "Password: " in prompt_input:
            assert registration_cmd.password == prompt_input["Password: "]

        if "Username: " in prompt_input:
            assert registration_cmd.username == prompt_input["Username: "]

        # assert that we prompted the user the number of times that we expected
        assert fake_prompt_user.call_count == len(prompt_input)

    def test_from_tool_opts_activation_key_empty_string(self, tool_opts, monkeypatch):
        monkeypatch.setattr(utils, "prompt_user", PromptUserLoopMocked())
        tool_opts.activation_key = "activation_key"

        registration_cmd = subscription.RegistrationCommand.from_tool_opts(tool_opts)

        assert registration_cmd.activation_key == "activation_key"
        assert registration_cmd.org == "test"
        assert utils.prompt_user.called == {"Organization: ": 2}

    def test_from_tool_opts_username_empty_string(self, tool_opts, monkeypatch):
        monkeypatch.setattr(utils, "prompt_user", PromptUserLoopMocked())

        registration_cmd = subscription.RegistrationCommand.from_tool_opts(tool_opts)

        assert registration_cmd.username == "test"
        assert registration_cmd.password == "test"
        assert utils.prompt_user.called == {"Username: ": 2, "Password: ": 2}

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
                "activation_key": "0xDEADBEEF",
                "org": "Local Organization",
            },
            {
                "rhsm_hostname": "localhost",
                "rhsm_port": "8800",
                "rhsm_prefix": "rhsm",
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
    def test_args(self, registration_kwargs):
        """Test that the argument list is generated correctly."""
        reg_cmd = subscription.RegistrationCommand(**registration_kwargs)

        args_list = reg_cmd.args

        # Assert that these are always added
        assert args_list[0] == "register"
        assert "--force" in args_list

        # Assert that password was not added to the args_list
        assert len([arg for arg in args_list if "password" in arg]) == 0

        # Assert the other args were added
        if (
            "rhsm_prefix" in registration_kwargs
            and "rhsm_port" in registration_kwargs
            and "rhsm_prefix" in registration_kwargs
        ):
            server_url = urllib.parse.urljoin(
                "https://{rhsm_hostname}:{rhsm_port}".format(**registration_kwargs),
                "{rhsm_prefix}".format(**registration_kwargs),
            )
            assert "--serverurl={0}".format(server_url) in args_list
        elif "rhsm_hostname" in registration_kwargs:
            assert "--serverurl=https://{rhsm_hostname}".format(**registration_kwargs) in args_list

        if "activation_key" in registration_kwargs:
            assert "--activationkey={activation_key}".format(**registration_kwargs) in args_list

        if "org" in registration_kwargs:
            assert "--org={org}".format(**registration_kwargs) in args_list

        if "username" in registration_kwargs:
            assert "--username={username}".format(**registration_kwargs) in args_list

        expected_length = len(registration_kwargs) + 2
        if "password" in registration_kwargs:
            expected_length -= 1
        if "rhsm_port" in registration_kwargs:
            expected_length -= 1
        if "rhsm_prefix" in registration_kwargs:
            expected_length -= 1

        assert len(args_list) == expected_length

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

    def test_calling_registration_command_activation_key(self, monkeypatch, mocked_rhsm_call_blocking):
        reg_cmd = subscription.RegistrationCommand(activation_key="0xDEADBEEF", org="Local Organization")
        reg_cmd()

        args = (
            "Local Organization",
            ["0xDEADBEEF"],
            {"force": True},
            {},
            "C",
        )
        mocked_rhsm_call_blocking.assert_called_once_with(
            "com.redhat.RHSM1",
            "/com/redhat/RHSM1/Register",
            "com.redhat.RHSM1.Register",
            "RegisterWithActivationKeys",
            "sasa{sv}a{sv}s",
            args,
            timeout=subscription.REGISTRATION_TIMEOUT,
        )

    def test_calling_registration_command_password(self, monkeypatch, mocked_rhsm_call_blocking):
        reg_cmd = subscription.RegistrationCommand(username="me_myself_and_i", password="a password")

        reg_cmd()

        args = (
            "",
            "me_myself_and_i",
            "a password",
            {"force": True},
            {},
            "C",
        )
        mocked_rhsm_call_blocking.assert_called_once_with(
            "com.redhat.RHSM1",
            "/com/redhat/RHSM1/Register",
            "com.redhat.RHSM1.Register",
            "Register",
            "sssa{sv}a{sv}s",
            args,
            timeout=subscription.REGISTRATION_TIMEOUT,
        )

    def test_calling_registration_command_with_connection_opts(self, monkeypatch, mocked_rhsm_call_blocking):
        reg_cmd = subscription.RegistrationCommand(
            username="me_myself_and_i",
            password="a password",
            rhsm_hostname="rhsm.redhat.com",
            rhsm_port="443",
            rhsm_prefix="/",
        )

        run_subprocess_mocked = mock.Mock(return_value=("", 0))
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

        run_subprocess_mocked = mock.Mock(return_value=("failed to set server.hostname", 1))
        monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

        with pytest.raises(
            ValueError,
            match="Error setting the subscription-manager connection configuration: failed to set server.hostname",
        ):
            reg_cmd()

        assert run_subprocess_mocked.called_once_with(
            ["subscription-manager", "config", "--server.hostname=rhsm.redhat.com"]
        )

    @pytest.mark.rhsm_returns((dbus.exceptions.DBusException(name="org.freedesktop.DBus.Error.NoReply"),))
    def test_registration_succeeds_but_dbus_returns_noreply(self, monkeypatch, mocked_rhsm_call_blocking):
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            mock.Mock(
                return_value=(
                    "system identity: 1234-56-78-9abc\n" "name: abc-123\n" "org name: Test\n" "org ID: 12345678910\n",
                    0,
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
            mock.Mock(
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


class TestReplaceSubscriptionManager(object):
    def test_replace_subscription_manager_skipped(self, monkeypatch, caplog, tool_opts):
        tool_opts.keep_rhsm = True
        monkeypatch.setattr(subscription, "unregister_system", mock.Mock())

        subscription.replace_subscription_manager()

        assert "Skipping due to the use of --keep-rhsm." in caplog.text
        subscription.unregister_system.assert_not_called()

    @pytest.mark.parametrize(
        ("isdir_return", "listdir_return"),
        (
            (True, []),
            (False, ["filename"]),
        ),
    )
    def test_replace_subscription_manager_rpms_not_available(self, monkeypatch, isdir_return, listdir_return):
        monkeypatch.setattr(os.path, "isdir", lambda x: isdir_return)
        monkeypatch.setattr(os, "listdir", lambda x: listdir_return)

        with pytest.raises(SystemExit):
            subscription.replace_subscription_manager()

    def test_replace_subscription_manager_unregister_failed(self, caplog, monkeypatch):
        mocked_unregister_system = mock.Mock(side_effect=subscription.UnregisterError("Unregister failed"))
        monkeypatch.setattr(subscription, "unregister_system", mocked_unregister_system)
        monkeypatch.setattr(subscription, "remove_original_subscription_manager", mock.Mock())
        monkeypatch.setattr(subscription, "install_rhel_subscription_manager", mock.Mock())
        monkeypatch.setattr(os.path, "isdir", lambda x: True)
        monkeypatch.setattr(os, "listdir", lambda x: ["filename"])

        subscription.replace_subscription_manager()

        assert caplog.records[-1].message == "Unregister failed"


class DownloadRHSMPkgsMocked(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0

    def __call__(self, pkgs_to_download, repo_path, repo_content):
        self.called += 1
        self.pkgs_to_download = pkgs_to_download
        self.repo_path = repo_path
        self.repo_content = repo_content


Version = namedtuple("Version", ["major", "minor"])


@pytest.mark.parametrize(
    (
        "version",
        "json_c_i686_installed",
        "pkgs_to_download",
    ),
    (
        (
            (6, 0),
            False,
            frozenset(
                (
                    "subscription-manager",
                    "subscription-manager-rhsm-certificates",
                    "subscription-manager-rhsm",
                )
            ),
        ),
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
    ),
)
def test_download_rhsm_pkgs(version, json_c_i686_installed, pkgs_to_download, monkeypatch):
    monkeypatch.setattr(system_info, "version", Version(*version))
    monkeypatch.setattr(system_info, "is_rpm_installed", lambda _: json_c_i686_installed)
    monkeypatch.setattr(subscription, "_download_rhsm_pkgs", DownloadRHSMPkgsMocked())
    monkeypatch.setattr(utils, "mkdir_p", DumbCallable())
    subscription.download_rhsm_pkgs()

    assert subscription._download_rhsm_pkgs.called == 1
    assert frozenset(subscription._download_rhsm_pkgs.pkgs_to_download) == pkgs_to_download


class TestUnregisteringSystem(object):
    @pytest.mark.parametrize(
        ("output", "ret_code", "expected"),
        (("", 0, "System unregistered successfully."),),
    )
    def test_unregister_system(self, output, ret_code, expected, monkeypatch, caplog):
        submgr_command = ("subscription-manager", "unregister")
        rpm_command = ("rpm", "--quiet", "-q", "subscription-manager")

        # Mock rpm command
        run_subprocess_mock = mock.Mock(
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
        run_subprocess_mock = mock.Mock(
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

        run_subprocess_mock = mock.Mock(
            side_effect=unit_tests.run_subprocess_side_effect(
                (rpm_command, ("", 1)),
            )
        )
        monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess_mock)
        subscription.unregister_system()
        assert "The subscription-manager package is not installed." in caplog.records[-1].message


@mock.patch("convert2rhel.toolopts.tool_opts.keep_rhsm", True)
def test_download_rhsm_pkgs_skipped(monkeypatch, caplog):
    monkeypatch.setattr(subscription, "_download_rhsm_pkgs", mock.Mock())
    subscription.download_rhsm_pkgs()
    assert "Skipping due to the use of --keep-rhsm." in caplog.text
    subscription._download_rhsm_pkgs.assert_not_called()


@pytest.mark.parametrize(
    ("submgr_installed", "keep_rhsm", "critical_string"),
    (
        (True, None, None),
        (False, True, "the subscription-manager needs to be installed"),
        (False, False, "The subscription-manager package is not installed correctly."),
    ),
)
def test_verify_rhsm_installed(submgr_installed, keep_rhsm, critical_string, monkeypatch, caplog):
    if keep_rhsm:
        monkeypatch.setattr(toolopts.tool_opts, "keep_rhsm", keep_rhsm)

    if submgr_installed:
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_objects",
            lambda _: [namedtuple("Pkg", ["name"])("subscription-manager")],
        )

        subscription.verify_rhsm_installed()

        assert "subscription-manager installed correctly." in caplog.text

    else:
        monkeypatch.setattr(pkghandler, "get_installed_pkg_objects", lambda _: None)

        with pytest.raises(SystemExit):
            subscription.verify_rhsm_installed()

        assert critical_string in caplog.text


@pytest.mark.parametrize(
    ("installed_pkgs", "not_tracked_pkgs", "skip_pkg_msg", "expected"),
    (
        (
            ["pkg1", "pkg2", "pkg3"],
            ["pkg3"],
            "Skipping tracking previously installed package: pkg3",
            "Tracking installed packages: ['pkg1', 'pkg2']",
        ),
        (["pkg1", "pkg2", "pkg3"], [], None, "Tracking installed packages: ['pkg1', 'pkg2', 'pkg3']"),
    ),
)
def test_track_installed_submgr_pkgs(installed_pkgs, not_tracked_pkgs, skip_pkg_msg, expected, monkeypatch, caplog):
    track_installed_pkgs_mock = mock.Mock()
    monkeypatch.setattr(backup.changed_pkgs_control, "track_installed_pkgs", track_installed_pkgs_mock)

    subscription.track_installed_submgr_pkgs(installed_pkgs, not_tracked_pkgs)

    if skip_pkg_msg:
        assert skip_pkg_msg in caplog.records[-2].message
    assert expected in caplog.records[-1].message
    assert track_installed_pkgs_mock.called == 1


# ----


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

    run_subprocess_mock = mock.Mock(
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

    run_subprocess_mock = mock.Mock(side_effect=[subprocess, subprocess2])
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

    run_subprocess_mock = mock.Mock(
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


class TestRollback(object):
    def test_rollback(self, monkeypatch):
        monkeypatch.setattr(subscription, "unregister_system", unit_tests.CountableMockObject())

        subscription.rollback()

        assert subscription.unregister_system.called == 1

    def test_rollback_unregister_skipped(self, monkeypatch, tool_opts, caplog):
        monkeypatch.setattr(subscription, "unregister_system", unit_tests.CountableMockObject())

        tool_opts.keep_rhsm = True

        subscription.rollback()

        assert subscription.unregister_system.called == 0
        assert "Skipping due to the use of --keep-rhsm." == caplog.records[-1].message

    def test_rollback_unregister_call_fails(self, monkeypatch, caplog):
        mocked_unregister_system = mock.Mock(side_effect=subscription.UnregisterError("Unregister failed"))
        monkeypatch.setattr(subscription, "unregister_system", mocked_unregister_system)

        subscription.rollback()

        assert mocked_unregister_system.called == 1
        assert "Unregister failed" == caplog.records[-1].message


@pytest.mark.parametrize(
    ("subprocess", "expected"),
    (
        (("output", 0), "RHEL repositories locked"),
        (("output", 1), "Locking RHEL repositories failed"),
    ),
)
@centos8
def test_lock_releasever_in_rhel_repositories(pretend_os, subprocess, expected, monkeypatch, caplog):
    cmd = ["subscription-manager", "release", "--set=%s" % system_info.releasever]
    run_subprocess_mock = mock.Mock(
        side_effect=unit_tests.run_subprocess_side_effect(
            (cmd, subprocess),
        )
    )
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )
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
    run_subprocess_mock = mock.Mock(
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
