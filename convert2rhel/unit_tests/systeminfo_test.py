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

# Required imports:


import logging
import os
import shutil

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

from convert2rhel import logger
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import utils
from convert2rhel.toolopts import tool_opts
from convert2rhel.systeminfo import system_info


class TestSysteminfo(unittest.TestCase):
    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output_tuple=('output', 0)):
            self.output_tuple = output_tuple
            self.called = 0
            self.used_args = []

        def __call__(self, *args, **kwargs):
            self.called += 1
            self.used_args.append(args)
            return self.output_tuple

    class PathExistsMocked(unit_tests.MockFunction):
        def __init__(self, return_value=True):
            self.return_value = return_value

        def __call__(self, filepath):
            return self.return_value

    class GenerateRpmVaMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self):
            self.called += 1

    class GetLoggerMocked(unit_tests.MockFunction):
        def __init__(self):
            self.task_msgs = []
            self.info_msgs = []
            self.warning_msgs = []
            self.critical_msgs = []

        def __call__(self, msg):
            return self

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def task(self, msg):
            self.task_msgs.append(msg)

        def info(self, msg):
            self.info_msgs.append(msg)

        def warn(self, msg, *args):
            self.warning_msgs.append(msg)

        def warning(self, msg, *args):
            self.warn(msg, *args)

        def debug(self, msg):
            pass

    class GetFileContentMocked(unit_tests.MockFunction):
        def __init__(self, data):
            self.data = data
            self.as_list = True
            self.called = 0

        def __call__(self, filename, as_list):
            self.called += 1
            return self.data[self.called -1]

    ##########################################################################

    def setUp(self):
        if os.path.exists(unit_tests.TMP_DIR):
            shutil.rmtree(unit_tests.TMP_DIR)
        os.makedirs(unit_tests.TMP_DIR)
        system_info.logger = logging.getLogger(__name__)

        self.rpmva_output_file = os.path.join(unit_tests.TMP_DIR, "rpm_va.log")

    def tearDown(self):
        if os.path.exists(unit_tests.TMP_DIR):
            shutil.rmtree(unit_tests.TMP_DIR)

    @unit_tests.mock(tool_opts, "no_rpm_va", True)
    def test_modified_rpm_files_diff_with_no_rpm_va(self):
        self.assertEqual(system_info.modified_rpm_files_diff(), None)

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(utils, "get_file_content", GetFileContentMocked(data=[['rpm1', 'rpm2'],
                                                                           ['rpm1', 'rpm2']]))
    def test_modified_rpm_files_diff_without_differences_after_conversion(self):
        self.assertEqual(system_info.modified_rpm_files_diff(), None)

    @unit_tests.mock(os.path, "exists", PathExistsMocked(True))
    @unit_tests.mock(tool_opts, "no_rpm_va", False)
    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(system_info, "logger", GetLoggerMocked())
    @unit_tests.mock(utils, "get_file_content", GetFileContentMocked(
        data=[['.M.......  g /etc/pki/ca-trust/extracted/java/cacerts'],
              ['.M.......  g /etc/pki/ca-trust/extracted/java/cacerts',
               'S.5....T.  c /etc/yum.conf']]))
    def test_modified_rpm_files_diff_with_differences_after_conversion(self):
        system_info.modified_rpm_files_diff()
        self.assertTrue(any('S.5....T.  c /etc/yum.conf' in elem for elem in system_info.logger.info_msgs))

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked(("rpmva\n", 0)))
    def test_generate_rpm_va(self):
        # Check that rpm -Va is executed (default) and stored into the specific file.
        system_info.generate_rpm_va()

        self.assertTrue(utils.run_subprocess.called > 0)
        self.assertEqual(utils.run_subprocess.used_args[0][0], "rpm -Va")
        self.assertTrue(os.path.isfile(self.rpmva_output_file))
        self.assertEqual(utils.get_file_content(self.rpmva_output_file), "rpmva\n")

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_generate_rpm_va_skip(self):
        # Check that rpm -Va is not called when the --no-rpm-va option is used.
        tool_opts.no_rpm_va = True
        system_info.generate_rpm_va()

        self.assertEqual(utils.run_subprocess.called, 0)
        self.assertFalse(os.path.exists(self.rpmva_output_file))
