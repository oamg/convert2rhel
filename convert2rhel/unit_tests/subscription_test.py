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

# Required imports:
import os
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

from convert2rhel import subscription
from convert2rhel import utils
from convert2rhel.toolopts import tool_opts


class TestSubscription(unittest.TestCase):
    class GetAvailSubsMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return [{'name': 'sample',
                     'available': True,
                     'ends': '31/12/2999',
                     'systype': 'sampletype',
                     'pool': 'samplepool'}]

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
            return [{'name': 'sample',
                     'available': True,
                     'ends': '31/12/2999',
                     'systype': 'sampletype',
                     'pool': 'samplepool'}]

    class LetUserChooseItemMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return 0

    class GetRegistrationCmdMocked(unit_tests.MockFunction):
        def __call__(self):
            return "subscription-manager register whatever-options"

    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, tuples=None):
            # you can specify sequence of return (object, return code) as
            # a list of tuple that will be consumed continuosly on the each
            # call; when the list is consumed or it is empty, the default
            # tuple is returned
            self.tuples = tuples
            self.default_tuple = ('output', 0)
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1
            if self.tuples:
                return self.tuples.pop(0)
            return self.default_tuple

    class RegisterSystemMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1

    class GetLoggerMocked(unit_tests.MockFunction):
        def __init__(self):
            self.info_msgs = []
            self.warning_msgs = []
            self.critical_msgs = []

        def __call__(self, msg):
            return self

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def info(self, msg):
            self.info_msgs.append(msg)

        def warning(self, msg):
            self.warning_msgs.append(msg)

        def debug(self, msg):
            pass

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

    ##########################################################################

    def setUp(self):
        tool_opts.__init__()

    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=False))
    def test_rhn_classic_not_exist(self):
        subscription.unregister_from_rhn_classic()
        self.assertEqual(len(subscription.logging.getLogger.info_msgs), 1)

    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=True))
    @unit_tests.mock(utils, "ask_to_continue", PromptUserMocked())
    @unit_tests.mock(subscription.rhn_reg_file, "remove", RemoveFileMocked())
    def test_rhn_classic_not_exist(self):
        subscription.unregister_from_rhn_classic()
        self.assertEqual(len(subscription.logging.getLogger.info_msgs), 0)
        self.assertEqual(len(subscription.logging.getLogger.warning_msgs), 1)

    def test_get_registration_cmd(self):
        tool_opts.username = 'user'
        tool_opts.password = 'pass with space'
        expected = \
            'subscription-manager register --force --username=user --password="pass with space"'
        self.assertEqual(subscription.get_registration_cmd(), expected)

    @unit_tests.mock(subscription, "get_avail_subs", GetAvailSubsMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_attach_subscription_available(self):
        self.assertEqual(subscription.attach_subscription(), True)

    @unit_tests.mock(subscription, "get_avail_subs", GetNoAvailSubsMocked())
    def test_attach_subscription_none_available(self):
        self.assertEqual(subscription.attach_subscription(), False)

    @unit_tests.mock(subscription, "register_system", RegisterSystemMocked())
    @unit_tests.mock(subscription, "get_avail_subs", GetAvailSubsMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_subscribe_system(self):
        tool_opts.username = 'user'
        tool_opts.password = 'pass'
        subscription.subscribe_system()
        self.assertEqual(subscription.register_system.called, 1)

    @unit_tests.mock(subscription, "register_system", RegisterSystemMocked())
    @unit_tests.mock(subscription, "get_avail_subs", GetNoAvailSubsOnceMocked())
    @unit_tests.mock(utils, "let_user_choose_item", LetUserChooseItemMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_subscribe_system_fail_once(self):
        tool_opts.username = 'user'
        tool_opts.password = 'pass'
        subscription.subscribe_system()
        self.assertEqual(subscription.register_system.called, 2)

    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked([("nope", 1)]))
    def test_register_system_fail_non_interactive(self):
        # Check the critical severity is logged when the credentials are given
        # on the cmdline but registration fails
        tool_opts.username = 'user'
        tool_opts.password = 'pass'
        tool_opts.credentials_thru_cli = True
        self.assertRaises(SystemExit, subscription.register_system)
        self.assertEqual(len(subscription.logging.getLogger.critical_msgs), 1)

    @unit_tests.mock(utils,
                     "run_subprocess",
                     RunSubprocessMocked(tuples=[("nope", 1), ("nope", 2), ("Success", 0)]))
    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(subscription, "get_registration_cmd", GetRegistrationCmdMocked())
    def test_register_system_fail_interactive(self):
        # Check the function tries to register multiple times without
        # critical log.
        tool_opts.credentials_thru_cli = False
        subscription.register_system()
        self.assertEqual(utils.run_subprocess.called, 3)
        self.assertEqual(len(subscription.logging.getLogger.critical_msgs), 0)

    def test_hiding_password(self):
        test_cmd = 'subscription-manager register --force ' \
                   '--username=jdoe --password="%s" --org=0123'
        pswds_to_test = [
            "my favourite password",
            "\\)(*&^%f %##@^%&*&^(",
            " ",
            ""
        ]
        for pswd in pswds_to_test:
            sanitized_cmd = subscription.hide_password(test_cmd % pswd)
            self.assertEqual(
                sanitized_cmd,
                'subscription-manager register --force '
                '--username=jdoe --password="*****" --org=0123')


    def test_rhsm_serverurl(self):
        tool_opts.username = 'user'
        tool_opts.password = 'pass'
        tool_opts.serverurl = 'url'
        expected = \
            'subscription-manager register --force --username=user --password="pass" --serverurl="url"'
        self.assertEqual(subscription.get_registration_cmd(), expected)

    class FakeSubscription:
        def __init__(self):
            self.subscription = (
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
                "Ends:              %s\n"
                "System Type:       Virtual\n"
            )
            self.dates_formats = [
                "26.07.2018",
                "26. 07. 2018",
                "26/07/2018",
                "H26.07.2018",
                "26-07-2018",
                "07.26.2018",
                "2018/07/26",
                "2018.07.26",
                "2018-07-26",
                "2018-26-07",
                "2018.26.07",
                "2018/26/07"
            ]

        def __call__(self, date):
            return self.subscription % date

    @unit_tests.mock(subscription.logging, "getLogger", GetLoggerMocked())
    def test_parse_sub_date(self):
        # Check that various formats of date don't affect parsing of SKU
        sku = self.FakeSubscription()
        for i in sku.dates_formats:
            self.assertEqual(subscription.parse_sub_attrs(sku(i))["ends"], i)
            self.assertEqual(len(subscription.logging.getLogger.critical_msgs), 0)
