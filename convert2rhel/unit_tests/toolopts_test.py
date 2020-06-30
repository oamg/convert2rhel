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


import sys

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
import convert2rhel.toolopts
from convert2rhel.toolopts import tool_opts


class TestToolopts(unittest.TestCase):
    def _params(params):  # pylint: disable=E0213
        return sys.argv[0:1] + params

    def setUp(self):
        tool_opts.__init__()

    @unit_tests.mock(sys, "argv", _params(["--username", "uname"]))
    def test_cmdline_interactive_username_without_passwd(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.username, "uname")
        self.assertFalse(tool_opts.credentials_thru_cli)

    @unit_tests.mock(sys, "argv", _params(["--password", "passwd"]))
    def test_cmdline_interactive_passwd_without_uname(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.password, "passwd")
        self.assertFalse(tool_opts.credentials_thru_cli)

    @unit_tests.mock(sys, "argv", _params(["--username", "uname",
                                           "--password", "passwd"]))
    def test_cmdline_non_ineractive_with_credentials(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.username, "uname")
        self.assertEqual(tool_opts.password, "passwd")
        self.assertTrue(tool_opts.credentials_thru_cli)

    @unit_tests.mock(sys, "argv", _params(["--serverurl", "url"]))
    def test_custom_serverurl(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.serverurl, "url")

    @unit_tests.mock(sys, "argv", _params(["--enablerepo", "foo"]))
    def test_cmdline_disablerepo_defaults_to_asterisk(self):
        convert2rhel.toolopts.CLI()
        self.assertEqual(tool_opts.enablerepo, ["foo"])
        self.assertEqual(tool_opts.disablerepo, ["*"])

    @unit_tests.mock(sys, "argv", _params(["--disable-submgr"]))
    def test_cmdline_exits_on_empty_enablerepo_with_disable_submgr(self):
        self.assertRaises(SystemExit, convert2rhel.toolopts.CLI)
