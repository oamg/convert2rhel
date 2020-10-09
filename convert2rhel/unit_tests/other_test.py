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

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

from convert2rhel import pkghandler
from convert2rhel import utils
from convert2rhel import logger


class TestOther(unittest.TestCase):

    def test_correct_constants(self):
        # Prevents unintentional change of constants
        self.assertEqual(utils.TMP_DIR, "/var/lib/convert2rhel/")
        self.assertEqual(utils.DATA_DIR, "/usr/share/convert2rhel/")
        self.assertEqual(pkghandler.MAX_YUM_CMD_CALLS, 2)
        self.assertEqual(logger.LOG_DIR, "/var/log/convert2rhel")
