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

import glob
import os
import shutil

from convert2rhel import cert
from convert2rhel.systeminfo import system_info
from convert2rhel import utils


class TestCert(unittest.TestCase):

    class GlobMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return [os.path.join(cert._redhat_release_cert_dir, "69.pem")]

    class MkdirPMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return

    class CopyMocked(unit_tests.MockFunction):
        def __call__(self, source, dest):
            self.source = source
            self.dest = dest

    base_data_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                  "..", "data", "5", "x86_64"))

    @unit_tests.mock(glob, "glob", GlobMocked())
    @unit_tests.mock(utils, "mkdir_p", MkdirPMocked())
    @unit_tests.mock(shutil, "copy", CopyMocked())
    @unit_tests.mock(system_info, "version", "5")
    @unit_tests.mock(utils, "data_dir", base_data_dir)
    def test_copy_cert_for_rhel_5(self):
        cert.copy_cert_for_rhel_5()
        self.assertEqual(shutil.copy.source,
                         os.path.join(cert._redhat_release_cert_dir, "69.pem"))
        self.assertEqual(shutil.copy.dest, cert._subscription_manager_cert_dir)
