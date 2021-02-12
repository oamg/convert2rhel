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
import re
import unittest

from convert2rhel import __version__, logger, pkghandler, utils

RPM_SPEC_VERSION_RE = re.compile(r"^Version: +(.+)$")


class TestOther(unittest.TestCase):
    def test_correct_constants(self):
        # Prevents unintentional change of constants
        self.assertEqual(utils.TMP_DIR, "/var/lib/convert2rhel/")
        self.assertEqual(utils.DATA_DIR, "/usr/share/convert2rhel/")
        self.assertEqual(pkghandler.MAX_YUM_CMD_CALLS, 2)
        self.assertEqual(logger.LOG_DIR, "/var/log/convert2rhel")


def test_package_version(pkg_root):
    # version should be a string
    assert isinstance(__version__, str)
    # version should be separated with dots, i.e. "1.1.1b"
    assert len(__version__.split(".")) > 1
    # versions specified in rpm spec and convert2rhel.__init__ should match
    with open(str(pkg_root / "packaging/convert2rhel.spec")) as spec_f:
        for line in spec_f:
            if RPM_SPEC_VERSION_RE.match(line):
                assert __version__ == RPM_SPEC_VERSION_RE.findall(line)[0]
                break
