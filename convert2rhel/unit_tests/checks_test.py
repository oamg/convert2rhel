# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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

from convert2rhel import checks, unit_tests
from convert2rhel.unit_tests import GetLoggerMocked


class TestChecks(unittest.TestCase):

    @unit_tests.mock(os.path, "exists", lambda x: x == "/sys/firmware/efi")
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    def test_check_uefi_efi_detected(self):
        self.assertRaises(SystemExit, checks.check_uefi)
        self.assertEqual(len(checks.logger.critical_msgs), 1)
        self.assertTrue("Conversion of UEFI systems is currently not supported" in checks.logger.critical_msgs[0])
        if checks.logger.debug_msgs:
            self.assertFalse("Converting BIOS system" in checks.logger.debug_msgs[0])


    @unit_tests.mock(os.path, "exists", lambda x: not x == "/sys/firmware/efi")
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    def test_check_uefi_bios_detected(self):
        checks.check_uefi()
        self.assertFalse(checks.logger.critical_msgs)
        self.assertTrue("Converting BIOS system" in checks.logger.debug_msgs[0])
