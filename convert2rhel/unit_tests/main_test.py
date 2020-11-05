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


import os

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

from convert2rhel import main
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import redhatrelease
from convert2rhel import repo
from convert2rhel import subscription
from convert2rhel import utils
from convert2rhel import pkghandler
from convert2rhel.toolopts import tool_opts

def mock_calls(class_or_module, method_name, mock_obj):
    return unit_tests.mock(class_or_module, method_name, mock_obj(method_name))

class TestMain(unittest.TestCase):

    class AskToContinueMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return

    eula_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                             "..", "data", "version-independent"))

    @unit_tests.mock(utils, "ask_to_continue", AskToContinueMocked())
    @unit_tests.mock(utils, "DATA_DIR", eula_dir)
    def test_user_to_accept_eula(self):
        main.user_to_accept_eula()

    class GetFileContentMocked(unit_tests.MockFunction):
        def __call__(self, filename):
            return utils.get_file_content_orig(unit_tests.NONEXISTING_FILE)

    class GetLoggerMocked(unit_tests.MockFunction):
        def __init__(self):
            self.info_msgs = []
            self.critical_msgs = []

        def __call__(self, msg):
            return self

        def task(self, msg):
            pass

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def info(self, msg):
            pass

        def debug(self, msg):
            pass

    class CallOrderMocked(unit_tests.MockFunction):
        calls = OrderedDict()
        def __init__(self, method_name):
            self.method_name = method_name

        def __call__(self, *args):
            self.add_call(self.method_name)
            return args

        @classmethod
        def add_call(cls, method_name):
            if method_name in cls.calls:
                cls.calls[method_name] += 1
            else:
                cls.calls[method_name] = 1

        @classmethod
        def reset(cls):
            cls.calls = OrderedDict()



    @unit_tests.mock(main.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(utils, "ask_to_continue", AskToContinueMocked())
    @unit_tests.mock(utils, "get_file_content", GetFileContentMocked())
    def test_user_to_accept_eula_nonexisting_file(self):
        self.assertRaises(SystemExit, main.user_to_accept_eula)
        self.assertEqual(len(main.logging.getLogger.critical_msgs), 1)

    @unit_tests.mock(utils.changed_pkgs_control, "restore_pkgs", unit_tests.CountableMockObject())
    @unit_tests.mock(redhatrelease.system_release_file, "restore", unit_tests.CountableMockObject())
    @unit_tests.mock(redhatrelease.yum_conf, "restore", unit_tests.CountableMockObject())
    @unit_tests.mock(subscription, "rollback", unit_tests.CountableMockObject())
    def test_rollback_changes(self):
        main.rollback_changes()
        self.assertEqual(utils.changed_pkgs_control.restore_pkgs.called, 1)
        self.assertEqual(redhatrelease.system_release_file.restore.called, 1)
        self.assertEqual(redhatrelease.yum_conf.restore.called, 1)
        self.assertEqual(subscription.rollback.called, 1)


    @unit_tests.mock(main.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "disable_submgr", False)
    @mock_calls(pkghandler, "remove_excluded_pkgs", CallOrderMocked)
    @mock_calls(redhatrelease, "install_release_pkg", CallOrderMocked)
    @mock_calls(redhatrelease.YumConf, "patch", CallOrderMocked)
    @mock_calls(pkghandler, "list_third_party_pkgs", CallOrderMocked)
    @mock_calls(subscription, "install_subscription_manager", CallOrderMocked)
    @mock_calls(subscription, "subscribe_system", CallOrderMocked)
    @mock_calls(repo, "get_rhel_repoids", CallOrderMocked)
    @mock_calls(subscription, "check_needed_repos_availability", CallOrderMocked)
    @mock_calls(subscription, "disable_repos", CallOrderMocked)
    @mock_calls(subscription, "enable_repos", CallOrderMocked)
    @mock_calls(subscription, "rename_repo_files", CallOrderMocked)
    def test_pre_ponr_conversion_order_with_rhsm(self):
        self.CallOrderMocked.reset()
        main.pre_ponr_conversion()

        intended_call_order = OrderedDict()
        intended_call_order["remove_excluded_pkgs"] = 1
        intended_call_order["install_release_pkg"] = 1
        intended_call_order["patch"] = 1
        intended_call_order["list_third_party_pkgs"] = 1
        intended_call_order["install_subscription_manager"] = 1
        intended_call_order["subscribe_system"] = 1
        intended_call_order["get_rhel_repoids"] = 1
        intended_call_order["check_needed_repos_availability"] = 1
        intended_call_order["disable_repos"] = 1
        intended_call_order["enable_repos"] = 1
        intended_call_order["rename_repo_files"] = 1

        # Merge the two together like a zipper, creates a tuple which we can assert with - including method call order!
        zipped_call_order = zip(intended_call_order.items(), self.CallOrderMocked.calls.items())
        for expected, actual in zipped_call_order:
            if expected[1] > 0:
                self.assertEqual(expected, actual)



    @unit_tests.mock(main.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "disable_submgr", False)
    @mock_calls(pkghandler, "remove_excluded_pkgs", CallOrderMocked)
    @mock_calls(redhatrelease, "install_release_pkg", CallOrderMocked)
    @mock_calls(redhatrelease.YumConf, "patch", CallOrderMocked)
    @mock_calls(pkghandler, "list_third_party_pkgs", CallOrderMocked)
    @mock_calls(subscription, "install_subscription_manager", CallOrderMocked)
    @mock_calls(subscription, "subscribe_system", CallOrderMocked)
    @mock_calls(repo, "get_rhel_repoids", CallOrderMocked)
    @mock_calls(subscription, "check_needed_repos_availability", CallOrderMocked)
    @mock_calls(subscription, "disable_repos", CallOrderMocked)
    @mock_calls(subscription, "enable_repos", CallOrderMocked)
    @mock_calls(subscription, "rename_repo_files", CallOrderMocked)
    def test_pre_ponr_conversion_order_without_rhsm(self):
        self.CallOrderMocked.reset()
        main.pre_ponr_conversion()

        intended_call_order = OrderedDict()
        intended_call_order["remove_excluded_pkgs"] = 1
        intended_call_order["install_release_pkg"] = 1
        intended_call_order["patch"] = 1
        intended_call_order["list_third_party_pkgs"] = 1

        # Do not expect these to be called - related to RHSM
        intended_call_order["install_subscription_manager"] = 0
        intended_call_order["subscribe_system"] = 0
        intended_call_order["get_rhel_repoids"] = 0
        intended_call_order["check_needed_repos_availability"] = 0
        intended_call_order["disable_repos"] = 0
        intended_call_order["enable_repos"] = 0
        intended_call_order["rename_repo_files"] = 0

        # Merge the two together like a zipper, creates a tuple which we can assert with - including method call order!
        zipped_call_order = zip(intended_call_order.items(), self.CallOrderMocked.calls.items())
        for expected, actual in zipped_call_order:
            if expected[1] > 0:
                self.assertEqual(expected, actual)
