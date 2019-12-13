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

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

import os

from convert2rhel import main
from convert2rhel import utils


class TestMain(unittest.TestCase):

    class ask_to_continue_mocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return

    eula_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                "..", "data", "version-independent"))

    @unit_tests.mock(utils, "ask_to_continue", ask_to_continue_mocked())
    @unit_tests.mock(utils, "data_dir", eula_dir)
    def test_user_to_accept_eula(self):
        main.user_to_accept_eula()

    class get_file_content_mocked(unit_tests.MockFunction):
        def __call__(self, filename):
            return utils.get_file_content_orig(unit_tests.nonexisting_file)

    class getLogger_mocked(unit_tests.MockFunction):
        def __init__(self):
            self.info_msgs = []
            self.critical_msgs = []

        def __call__(self, msg):
            return self

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def info(self, msg):
            pass

        def debug(self, msg):
            pass

    @unit_tests.mock(main.logging, "getLogger", getLogger_mocked())
    @unit_tests.mock(utils, "ask_to_continue", ask_to_continue_mocked())
    @unit_tests.mock(utils, "get_file_content", get_file_content_mocked())
    def test_user_to_accept_eula_nonexisting_file(self):
        self.assertRaises(SystemExit, main.user_to_accept_eula)
        self.assertEqual(len(main.logging.getLogger.critical_msgs), 1)
