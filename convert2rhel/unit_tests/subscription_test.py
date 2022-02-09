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
import sys
import unittest

from collections import namedtuple

import pytest

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import pkghandler, subscription, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import GetLoggerMocked, run_subprocess_side_effect


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


class DumbCallable(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0

    def __call__(self, *args, **kwargs):
        self.called += 1


class TestSubscription(unittest.TestCase):
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

    class LetUserChooseItemMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1
            return 0

    class GetRegistrationCmdMocked(unit_tests.MockFunction):
        def __call__(self):
            return "subscription-manager register whatever-options"

    class CallRegistrationCmdMocked(unit_tests.MockFunction):
        def __init__(self, cmd):
            self.cmd = cmd

        def __call__(self, cmd):
            self.cmd = cmd
            return ("User interrupted process.", 0)

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

    class IsFileMocked(unit_tests.MockFunction):
        def __init__(self, is_file):
            self.is_file = is_file

        def __call__(self, *args, **kwargs):
            return self.is_file

    class PromptUserMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return True

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

    def test_get_registration_cmd(self):
        tool_opts.username = "user"
        tool_opts.password = "pass with space"
        expected = ["subscription-manager", "register", "--force", "--username=user", "--password=pass with space"]
        self.assertEqual(subscription.get_registration_cmd(), expected)

    @unit_tests.mock(subscription, "get_avail_subs", GetOneSubMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_attach_subscription_one_sub_available(self):
        self.assertEqual(subscription.attach_subscription(), True)
        self.assertEqual(utils.let_user_choose_item.called, 0)

    def test_get_registration_cmd_activation_key(self):
        tool_opts.activation_key = "activation_key"
        tool_opts.org = "org"
        expected = ["subscription-manager", "register", "--force", "--activationkey=activation_key", "--org=org"]
        self.assertEqual(subscription.get_registration_cmd(), expected)

    @unit_tests.mock(utils, "prompt_user", PromptUserLoopMocked())
    def test_get_registration_cmd_activation_key_empty_string(self):
        tool_opts.activation_key = "activation_key"
        expected = ["subscription-manager", "register", "--force", "--activationkey=activation_key", "--org=test"]
        self.assertEqual(subscription.get_registration_cmd(), expected)
        self.assertEqual(utils.prompt_user.called, {"Organization: ": 2})

    @unit_tests.mock(utils, "prompt_user", PromptUserLoopMocked())
    def test_get_registration_cmd_empty_string(self):
        expected = ["subscription-manager", "register", "--force", "--username=test", "--password=test"]
        self.assertEqual(subscription.get_registration_cmd(), expected)
        self.assertEqual(utils.prompt_user.called, {"Username: ": 2, "Password: ": 2})

    @unit_tests.mock(subscription, "get_avail_subs", GetOneSubMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_attach_subscription_one_sub_available(self):
        self.assertEqual(subscription.attach_subscription(), True)
        self.assertEqual(utils.let_user_choose_item.called, 0)

    @unit_tests.mock(subscription, "get_avail_subs", GetAvailSubsMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_attach_subscription_multiple_subs_available(self):
        self.assertEqual(subscription.attach_subscription(), True)
        self.assertEqual(utils.let_user_choose_item.called, 1)

    @unit_tests.mock(subscription, "get_avail_subs", GetAvailSubsMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(tool_opts, "activation_key", "dummy_activate_key")
    @unit_tests.mock(subscription, "loggerinst", GetLoggerMocked())
    def test_attach_subscription_available_with_activation_key(self):
        self.assertEqual(subscription.attach_subscription(), True)
        self.assertEqual(len(subscription.loggerinst.info_msgs), 1)

    @unit_tests.mock(subscription, "get_avail_subs", GetNoAvailSubsMocked())
    def test_attach_subscription_none_available(self):
        self.assertEqual(subscription.attach_subscription(), False)

    @unit_tests.mock(subscription, "register_system", DumbCallable())
    @unit_tests.mock(subscription, "get_avail_subs", GetAvailSubsMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_subscribe_system(self):
        tool_opts.username = "user"
        tool_opts.password = "pass"
        subscription.subscribe_system()
        self.assertEqual(subscription.register_system.called, 1)

    @unit_tests.mock(subscription, "register_system", DumbCallable())
    @unit_tests.mock(subscription, "get_avail_subs", GetNoAvailSubsOnceMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_subscribe_system_fail_once(self):
        tool_opts.username = "user"
        tool_opts.password = "pass"
        subscription.subscribe_system()
        self.assertEqual(subscription.register_system.called, 2)

    @unit_tests.mock(subscription, "loggerinst", GetLoggerMocked())
    @unit_tests.mock(subscription, "MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE", 1)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked([("nope", 1)]))
    @unit_tests.mock(subscription, "sleep", mock.Mock())
    def test_register_system_fail_non_interactive(self):
        # Check the critical severity is logged when the credentials are given
        # on the cmdline but registration fails
        tool_opts.username = "user"
        tool_opts.password = "pass"
        tool_opts.credentials_thru_cli = True
        self.assertRaises(SystemExit, subscription.register_system)
        self.assertEqual(len(subscription.loggerinst.critical_msgs), 1)

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked(tuples=[("nope", 1), ("nope", 2), ("Success", 0)]))
    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(subscription, "get_registration_cmd", GetRegistrationCmdMocked())
    @unit_tests.mock(subscription, "sleep", mock.Mock())
    def test_register_system_fail_interactive(self):
        # Check the function tries to register multiple times without
        # critical log.
        tool_opts.credentials_thru_cli = False
        subscription.register_system()
        self.assertEqual(utils.run_subprocess.called, 3)
        self.assertEqual(len(subscription.logging.getLogger.critical_msgs), 0)

    @unit_tests.mock(subscription, "get_registration_cmd", GetRegistrationCmdMocked())
    @unit_tests.mock(subscription, "call_registration_cmd", CallRegistrationCmdMocked("cmd"))
    def test_register_system_fail_with_keyboardinterrupt(self):
        self.assertRaises(KeyboardInterrupt, subscription.register_system)

    def test_hiding_password(self):
        test_cmd = "subscription-manager register --force " '--username=jdoe --password="%s" --org=0123'
        pswds_to_test = ["my favourite password", "\\)(*&^%f %##@^%&*&^(", " ", ""]
        for pswd in pswds_to_test:
            sanitized_cmd = subscription.hide_password(test_cmd % pswd)
            self.assertEqual(
                sanitized_cmd, "subscription-manager register --force " '--username=jdoe --password="*****" --org=0123'
            )

    def test_rhsm_serverurl(self):
        tool_opts.username = "user"
        tool_opts.password = "pass"
        tool_opts.serverurl = "url"
        expected = [
            "subscription-manager",
            "register",
            "--force",
            "--username=user",
            "--password=pass",
            "--serverurl=url",
        ]
        self.assertEqual(subscription.get_registration_cmd(), expected)

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

    @unit_tests.mock(subscription, "unregister_system", unit_tests.CountableMockObject())
    def test_rollback(self):
        subscription.rollback()
        self.assertEqual(subscription.unregister_system.called, 1)

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
        self.assertTrue("Needed RHEL repos are available" in logging.Logger.info.msg)

        subscription.check_needed_repos_availability(["rhel_z"])
        self.assertTrue("rhel_z repository is not available" in logging.Logger.warning.msg)

    @unit_tests.mock(logging.Logger, "warning", LogMocked())
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(subscription, "get_avail_repos", lambda: [])
    def test_check_needed_repos_availability_no_repo_available(self):
        subscription.check_needed_repos_availability(["rhel"])
        self.assertTrue("rhel repository is not available" in logging.Logger.warning.msg)

    @unit_tests.mock(os.path, "isdir", lambda x: True)
    @unit_tests.mock(os, "listdir", lambda x: [])
    def test_replace_subscription_manager_rpms_not_available(self):
        self.assertRaises(SystemExit, subscription.replace_subscription_manager)

        os.path.isdir = lambda x: False
        os.listdir = lambda x: ["filename"]
        self.assertRaises(SystemExit, subscription.replace_subscription_manager)

    @unit_tests.mock(pkghandler, "get_installed_pkg_objects", lambda _: [namedtuple("Pkg", ["name"])("submgr")])
    @unit_tests.mock(pkghandler, "print_pkg_info", lambda x: None)
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(utils, "remove_pkgs", DumbCallable())
    def test_remove_original_subscription_manager(self):
        subscription.remove_original_subscription_manager()
        self.assertEqual(utils.remove_pkgs.called, 1)
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkg_objects",
        lambda _: [namedtuple("Pkg", ["name"])("subscription-manager-initial-setup-addon")],
    )
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(8, 5))
    @unit_tests.mock(system_info, "id", "centos")
    @unit_tests.mock(pkghandler, "print_pkg_info", lambda x: None)
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(utils, "remove_pkgs", DumbCallable())
    def test_remove_original_subscription_manager_missing_package_ol_85(self):
        subscription.remove_original_subscription_manager()
        self.assertEqual(utils.remove_pkgs.called, 2)

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
    @unit_tests.mock(utils.changed_pkgs_control, "track_installed_pkgs", DumbCallable())
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
        "pkgs_to_download",
    ),
    (
        (
            (6, 0),
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
    ),
)
def test_download_rhsm_pkgs(version, pkgs_to_download, monkeypatch):
    monkeypatch.setattr(system_info, "version", Version(*version))
    monkeypatch.setattr(subscription, "_download_rhsm_pkgs", DownloadRHSMPkgsMocked())
    monkeypatch.setattr(utils, "mkdir_p", DumbCallable())
    subscription.download_rhsm_pkgs()

    assert subscription._download_rhsm_pkgs.called == 1
    assert frozenset(subscription._download_rhsm_pkgs.pkgs_to_download) == pkgs_to_download


class TestUnregisteringSystem:
    @pytest.mark.parametrize(
        ("output", "ret_code", "expected"),
        (("", 0, "System unregistered successfully."), ("Failed to unregister.", 1, "System unregistration failed")),
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

    def test_unregister_system_submgr_not_found(self, monkeypatch, caplog):
        rpm_command = "rpm --quiet -q subscription-manager"
        run_subprocess_mock = mock.Mock(
            side_effect=unit_tests.run_subprocess_side_effect(
                ((rpm_command,), ("", 1)),
            )
        )
        monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess_mock)
        subscription.unregister_system()
        assert "The subscription-manager package is not installed." in caplog.records[-1].message

    def test_unregister_system_keep_rhsm(self, monkeypatch, caplog):
        monkeypatch.setattr(tool_opts, "keep_rhsm", value=True)
        subscription.unregister_system()
        assert "Skipping due to the use of --keep-rhsm." in caplog.records[-1].message

    @mock.patch("convert2rhel.toolopts.tool_opts.keep_rhsm", True)
    def test_unregister_system_skipped(self, monkeypatch, caplog):
        monkeypatch.setattr(pkghandler, "get_installed_pkg_objects", mock.Mock())
        subscription.unregister_system()
        assert "Skipping due to the use of --keep-rhsm." in caplog.text
        pkghandler.get_installed_pkg_objects.assert_not_called()


@mock.patch("convert2rhel.toolopts.tool_opts.keep_rhsm", True)
def test_replace_subscription_manager_skipped(monkeypatch, caplog):
    monkeypatch.setattr(subscription, "unregister_system", mock.Mock())
    subscription.replace_subscription_manager()
    assert "Skipping due to the use of --keep-rhsm." in caplog.text
    subscription.unregister_system.assert_not_called()


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
        monkeypatch.setattr(tool_opts, "keep_rhsm", keep_rhsm)

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
    monkeypatch.setattr(utils.changed_pkgs_control, "track_installed_pkgs", track_installed_pkgs_mock)

    subscription.track_installed_submgr_pkgs(installed_pkgs, not_tracked_pkgs)

    if skip_pkg_msg:
        assert skip_pkg_msg in caplog.records[-2].message
    assert expected in caplog.records[-1].message
    assert track_installed_pkgs_mock.called == 1
