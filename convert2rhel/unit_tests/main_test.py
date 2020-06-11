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

from convert2rhel import main
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import redhatrelease
from convert2rhel import subscription
from convert2rhel import utils


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

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def info(self, msg):
            pass

        def debug(self, msg):
            pass

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
