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

import glob
import unittest

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import redhatrelease, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


class TestRedHatRelease(unittest.TestCase):

    supported_rhel_versions = ["6", "7", "8"]

    class DumbMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            pass

    class GlobMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return [unit_tests.TMP_DIR + "redhat-release/pkg1.rpm",
                    unit_tests.TMP_DIR + "redhat-release/pkg2.rpm",
                    "Server/redhat-release-7/pkg1.rpm",
                    "Server/redhat-release-7/pkg2.rpm"]

    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self):
            self.cmd = None

        def __call__(self, cmd, print_cmd=True, print_output=True):
            self.cmd = cmd
            return "Test output", 0

    @unit_tests.mock(redhatrelease.YumConf, "_yum_conf_path", unit_tests.DUMMY_FILE)
    def test_get_yum_conf_content(self):
        yum_conf = redhatrelease.YumConf()

        self.assertTrue("Dummy file to read" in yum_conf._yum_conf_content)

    @unit_tests.mock(redhatrelease.YumConf, "_yum_conf_path", unit_tests.DUMMY_FILE)
    @unit_tests.mock(system_info, "version", "to_be_changed")
    def test_patch_yum_conf_missing_distroverpkg(self):
        yum_conf = redhatrelease.YumConf()
        yum_conf._yum_conf_content = YUM_CONF_WITHOUT_DISTROVERPKG

        for version in self.supported_rhel_versions:
            system_info.version = version

            # Call just this function to avoid unmockable built-in write func
            yum_conf._comment_out_distroverpkg_tag()

            self.assertFalse("distroverpkg=" in yum_conf._yum_conf_content)
            self.assertEqual(yum_conf._yum_conf_content.count("distroverpkg="), 0)

    @unit_tests.mock(redhatrelease.YumConf, "_yum_conf_path", unit_tests.DUMMY_FILE)
    @unit_tests.mock(system_info, "version", "to_be_changed")
    def test_patch_yum_conf_existing_distroverpkg(self):
        yum_conf = redhatrelease.YumConf()
        yum_conf._yum_conf_content = YUM_CONF_WITH_DISTROVERPKG

        for version in self.supported_rhel_versions:
            system_info.version = version

            # Call just this function to avoid unmockable built-in write func
            yum_conf._comment_out_distroverpkg_tag()

            self.assertTrue("#distroverpkg=" in yum_conf._yum_conf_content)
            self.assertEqual(yum_conf._yum_conf_content.count("#distroverpkg="), 1)


YUM_CONF_WITHOUT_DISTROVERPKG = """[main]
installonly_limit=3

#  This is the default"""

YUM_CONF_WITH_DISTROVERPKG = """[main]
installonly_limit=3
distroverpkg=centos-release

#  This is the default"""
