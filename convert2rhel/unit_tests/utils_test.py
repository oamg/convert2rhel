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


import re
import os

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import utils


class TestUtils(unittest.TestCase):
    class DummyFuncMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, *args, **kargs):
            self.called += 1

    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output="Test output", ret_code=0):
            self.cmd = ""
            self.cmds = ""
            self.called = 0
            self.output = output
            self.ret_code = ret_code

        def __call__(self, cmd, print_cmd=True, print_output=True):
            self.cmd = cmd
            self.cmds += "%s\n" % cmd
            self.called += 1
            return self.output, self.ret_code

    class DummyGetUID(unit_tests.MockFunction):
        def __init__(self, uid):
            self.uid = uid

        def __call__(self, *args, **kargs):
            return self.uid

    @unit_tests.mock(os, "geteuid", DummyGetUID(1000))
    def test_require_root_is_not_root(self):
        self.assertRaises(SystemExit, utils.require_root)

    @unit_tests.mock(os, "geteuid", DummyGetUID(0))
    def test_require_root_is_root(self):
        self.assertEqual(utils.require_root(), None)

    def test_track_installed_pkg(self):
        control = utils.ChangedRPMPackagesController()
        pkgs = ['pkg1', 'pkg2', 'pkg3']
        for pkg in pkgs:
            control.track_installed_pkg(pkg)
        self.assertEqual(control.installed_pkgs, pkgs)

    @unit_tests.mock(utils.RestorablePackage, "backup", DummyFuncMocked())
    def test_backup_and_track_removed_pkg(self):
        control = utils.ChangedRPMPackagesController()
        pkgs = ['pkg1', 'pkg2', 'pkg3']
        for pkg in pkgs:
            control.backup_and_track_removed_pkg(pkg)
        self.assertEqual(utils.RestorablePackage.backup.called, len(pkgs))
        self.assertEqual(len(control.removed_pkgs), len(pkgs))

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_remove_pkgs_with_empty_list(self):
        utils.remove_pkgs([])
        self.assertEqual(utils.run_subprocess.called, 0)

    @unit_tests.mock(utils.ChangedRPMPackagesController,
                     "backup_and_track_removed_pkg",
                     DummyFuncMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_remove_pkgs_without_backup(self):
        pkgs = ['pkg1', 'pkg2', 'pkg3']
        utils.remove_pkgs(pkgs, False)
        self.assertEqual(
            utils.ChangedRPMPackagesController.backup_and_track_removed_pkg.called, 0)

        self.assertEqual(utils.run_subprocess.called, len(pkgs))

        rpm_remove_cmd = "rpm -e --nodeps"
        self.assertTrue(re.search(r"^%s pkg" % rpm_remove_cmd,
                                  utils.run_subprocess.cmds, re.MULTILINE))

    @unit_tests.mock(utils.ChangedRPMPackagesController,
                     "backup_and_track_removed_pkg",
                     DummyFuncMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_remove_pkgs_with_backup(self):
        pkgs = ['pkg1', 'pkg2', 'pkg3']
        utils.remove_pkgs(pkgs)
        self.assertEqual(
            utils.ChangedRPMPackagesController.backup_and_track_removed_pkg.called, len(pkgs))

        self.assertEqual(utils.run_subprocess.called, len(pkgs))

        rpm_remove_cmd = "rpm -e --nodeps"
        self.assertTrue(re.search(r"^%s pkg" % rpm_remove_cmd,
                                  utils.run_subprocess.cmds, re.MULTILINE))

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_install_pkgs_with_empty_list(self):
        utils.install_pkgs([])
        self.assertEqual(utils.run_subprocess.called, 0)

    @unit_tests.mock(utils.ChangedRPMPackagesController,
                     "track_installed_pkg",
                     DummyFuncMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_install_pkgs_without_replace(self):
        pkgs = ['pkg1', 'pkg2', 'pkg3']
        utils.install_pkgs(pkgs)
        self.assertEqual(
            utils.ChangedRPMPackagesController.track_installed_pkg.called, len(pkgs))

        self.assertEqual(utils.run_subprocess.called, 1)
        self.assertEqual("rpm -i pkg1 pkg2 pkg3", utils.run_subprocess.cmd)

    @unit_tests.mock(utils.ChangedRPMPackagesController,
                     "track_installed_pkg",
                     DummyFuncMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_install_pkgs_with_replace(self):
        pkgs = ['pkg1', 'pkg2', 'pkg3']
        utils.install_pkgs(pkgs, True)
        self.assertEqual(
            utils.ChangedRPMPackagesController.track_installed_pkg.called, len(pkgs))

        self.assertEqual(utils.run_subprocess.called, 1)
        self.assertEqual("rpm -i --replacepkgs pkg1 pkg2 pkg3", utils.run_subprocess.cmd)

    def test_run_subprocess(self):
        output, code = utils.run_subprocess("echo foobar")

        self.assertEqual(output, "foobar\n")
        self.assertEqual(code, 0)

        output, code = utils.run_subprocess("sh -c 'exit 56'")  # a command that just returns 56

        self.assertEqual(output, "")
        self.assertEqual(code, 56)

    DOWNLOADED_RPM_NVRA = "kernel-4.18.0-193.28.1.el8_2.x86_64"
    DOWNLOADED_RPM_NEVRA = "7:%s" % DOWNLOADED_RPM_NVRA
    DOWNLOADED_RPM_FILENAME = "%s.rpm" % DOWNLOADED_RPM_NVRA

    YUMDOWNLOADER_OUTPUTS = [
        "Last metadata expiration check: 2:47:36 ago on Thu 22 Oct 2020 06:07:08 PM CEST.\n"
        "%s         2.7 MB/s | 2.8 MB     00:01" % DOWNLOADED_RPM_FILENAME,
        "/var/lib/convert2rhel/%s already exists and appears to be complete" % DOWNLOADED_RPM_FILENAME,
        "using local copy of %s" % DOWNLOADED_RPM_NEVRA,
        "[SKIPPED] %s: Already downloaded" % DOWNLOADED_RPM_FILENAME
    ]

    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=0))
    @unit_tests.mock(utils, "get_rpm_path_from_yumdownloader_output", lambda x, y, z: "/path/test.rpm")
    def test_download_pkg_success_with_all_params(self):
        dest = "/test dir/"
        disablerepo = "x"
        enablerepo = "y"
        path = utils.download_pkg("kernel", dest=dest, disablerepo=disablerepo, enablerepo=enablerepo)

        self.assertEqual('yumdownloader -v --disablerepo=%s --enablerepo=%s --destdir="%s" kernel'
                         % (disablerepo, enablerepo, dest),
                         utils.run_cmd_in_pty.cmd)
        self.assertTrue(path)  # path is not None (which is the case of unsuccessful download)

    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=1))
    def test_download_pkg_failed_download(self):
        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

    @unit_tests.mock(utils, "run_cmd_in_pty", RunSubprocessMocked(ret_code=0))
    def test_download_pkg_incorrect_output(self):
        utils.run_cmd_in_pty.output = "bogus"

        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

        utils.run_cmd_in_pty.output = ""

        path = utils.download_pkg("kernel")

        self.assertEqual(path, None)

    def test_get_rpm_path_from_yumdownloader_output(self):
        for output in self.YUMDOWNLOADER_OUTPUTS:
            utils.run_cmd_in_pty.output = output

            path = utils.get_rpm_path_from_yumdownloader_output("cmd not important", output, utils.TMP_DIR)

            self.assertEqual(path, os.path.join(utils.TMP_DIR, self.DOWNLOADED_RPM_FILENAME))
