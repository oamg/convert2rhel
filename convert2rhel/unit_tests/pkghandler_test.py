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
import os
import re
import sys
import rpm

from convert2rhel import logger
from convert2rhel import pkghandler
from convert2rhel import pkgmanager
from convert2rhel import utils
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


class TestPkgHandler(unit_tests.ExtendedTestCase):
    class GetInstalledPkgsWithFingerprintMocked(unit_tests.MockFunction):
        def __init__(self, data=None):
            self.data = data
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1
            return self.data

    class CallYumCmdMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.return_code = 0
            self.return_string = "Test output"
            self.fail_once = False
            self.command = None

        def __call__(self, command, *args, **kwargs):
            if self.fail_once and self.called == 0:
                self.return_code = 1
            if self.fail_once and self.called > 0:
                self.return_code = 0
            self.called += 1
            self.command = command
            return self.return_string, self.return_code

    class GetInstalledPkgsByFingerprintMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return ["pkg1", "pkg2"]

    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output_text="Test output"):
            self.cmd = ""
            self.cmds = ""
            self.called = 0
            self.output = output_text
            self.ret_code = 0

        def __call__(self, cmd, print_cmd=True, print_output=True):
            self.cmd = cmd
            self.cmds += "%s\n" % cmd
            self.called += 1
            return self.output, self.ret_code

    class IsFileMocked(unit_tests.MockFunction):
        def __init__(self, is_file):
            self.is_file = is_file

        def __call__(self, *args, **kwargs):
            return self.is_file

    class DumbCallableObject(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return

    class SysExitCallableObject(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            sys.exit(1)

    class GetSizeMocked(unit_tests.MockFunction):
        def __init__(self, file_size):
            self.file_size = file_size

        def __call__(self, *args, **kwargs):
            return self.file_size

    class GetLoggerMocked(unit_tests.MockFunction):
        def __init__(self):
            self.info_msgs = []
            self.warning_msgs = []

        def __call__(self, msg):
            return self

        def info(self, msg):
            self.info_msgs.append(msg)

        def warn(self, msg, *args):
            self.warning_msgs.append(msg)

        def warning(self, msg, *args):
            self.warn(msg, *args)

        def debug(self, msg):
            pass


    @unit_tests.mock(pkghandler.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=False))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=0))
    def test_clear_versionlock_plugin_not_enabled(self):
        self.assertFalse(pkghandler.clear_versionlock())
        self.assertEqual(len(pkghandler.logging.getLogger.info_msgs), 1)
        self.assertEqual(pkghandler.logging.getLogger.info_msgs, ['Usage of YUM/DNF versionlock plugin not detected.'])


    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=True))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=1))
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    @unit_tests.mock(utils.RestorableFile, "backup", DumbCallableObject)
    @unit_tests.mock(utils.RestorableFile, "restore", DumbCallableObject)
    def test_clear_versionlock_user_says_yes(self):
        pkghandler.clear_versionlock()
        self.assertEqual(pkghandler.call_yum_cmd.called, 1)
        self.assertEqual(pkghandler.call_yum_cmd.command, "versionlock clear")

    @unit_tests.mock(utils, "ask_to_continue", SysExitCallableObject())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=True))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=1))
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_clear_versionlock_user_says_no(self):
        self.assertRaises(SystemExit, pkghandler.clear_versionlock)
        self.assertEqual(pkghandler.call_yum_cmd.called, 0)

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_call_yum_cmd(self):
        pkghandler.call_yum_cmd("install")

        self.assertEqual(utils.run_subprocess.cmd, "yum install -y")

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_call_yum_cmd_w_downgrades_continuous_fail(self):
        pkghandler.call_yum_cmd.return_code = 1

        self.assertRaises(SystemExit, pkghandler.call_yum_cmd_w_downgrades, "test_cmd", ["fingerprint"])
        self.assertEqual(pkghandler.call_yum_cmd.called, pkghandler.MAX_YUM_CMD_CALLS)

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(tool_opts, "disable_submgr", True)
    @unit_tests.mock(tool_opts, "disablerepo", ['*'])
    @unit_tests.mock(tool_opts, "enablerepo", ['rhel-7-extras-rpm'])
    def test_call_yum_cmd_with_disablerepo_and_enablerepo(self):
        pkghandler.call_yum_cmd("install")

        self.assertEqual(utils.run_subprocess.cmd,
                         "yum install -y --disablerepo=* --enablerepo=rhel-7-extras-rpm")

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(system_info, "submgr_enabled_repos", ['rhel-7-extras-rpm'])
    @unit_tests.mock(tool_opts, "enablerepo", ['not-to-be-used-in-the-yum-call'])
    def test_call_yum_cmd_with_submgr_enabled_repos(self):
        pkghandler.call_yum_cmd("install")

        self.assertEqual(utils.run_subprocess.cmd,
                         "yum install -y --enablerepo=rhel-7-extras-rpm")
        
    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint",
                     GetInstalledPkgsByFingerprintMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_call_yum_cmd_w_downgrades_correct_cmd(self):
        pkghandler.call_yum_cmd_w_downgrades("update", ["fingerprint"])

        self.assertEqual(utils.run_subprocess.cmd, "yum update -y pkg1 pkg2")

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint", lambda x: ["pkg"])
    def test_call_yum_cmd_w_downgrades_one_fail(self):
        pkghandler.call_yum_cmd.fail_once = True

        pkghandler.call_yum_cmd_w_downgrades("test_cmd", ["fingerprint"])

        self.assertEqual(pkghandler.call_yum_cmd.called, 2)

    def test_get_problematic_pkgs(self):
        error_pkgs = pkghandler.get_problematic_pkgs("", [])
        self.assertEqual(error_pkgs, [])

        error_pkgs = pkghandler.get_problematic_pkgs(YUM_PROTECTED_ERROR, [])
        self.assertIn("systemd", error_pkgs)
        self.assertIn("yum", error_pkgs)

        error_pkgs = pkghandler.get_problematic_pkgs(YUM_REQUIRES_ERROR, [])
        self.assertIn("libreport-anaconda", error_pkgs)
        self.assertIn("abrt-cli", error_pkgs)
        self.assertIn("libreport-plugin-rhtsupport", error_pkgs)

        error_pkgs = pkghandler.get_problematic_pkgs(YUM_MULTILIB_ERROR, [])
        self.assertIn("openldap", error_pkgs)
        self.assertIn("p11-kit", error_pkgs)

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_resolve_dep_errors_one_downgrade_fixes_the_error(self):
        pkghandler.call_yum_cmd.fail_once = True

        pkghandler.resolve_dep_errors(YUM_PROTECTED_ERROR, [])

        self.assertEqual(pkghandler.call_yum_cmd.called, 1)

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_resolve_dep_errors_unable_to_fix_by_downgrades(self):
        pkghandler.call_yum_cmd.return_code = 1
        pkghandler.call_yum_cmd.return_string = YUM_MULTILIB_ERROR

        pkghandler.resolve_dep_errors(YUM_PROTECTED_ERROR, [])

        # Firts call of the resolve_dep_errors, pkgs from protected error
        # are detected, the second call pkgs from multilib error are detected,
        # the third call yum_cmd is not called anymore, because the
        # problematic packages then remain the same (simulating that the
        # downgrades do not solve the yum errors)
        self.assertEqual(pkghandler.call_yum_cmd.called, 2)

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_resolve_dep_errors_unable_to_detect_problematic_pkgs(self):
        # Even though resolve_dep_errors was called (meaning that the previous
        # yum call ended with non-zero status), the string returned by yum
        # does not hold information recognizable by get_problematic_pkgs
        pkghandler.resolve_dep_errors("No info about problematic pkgs.", [])

        self.assertEqual(pkghandler.call_yum_cmd.called, 0)

    class TestPkgObj(object):
        class PkgObjHdr(object):
            def sprintf(self, *args, **kwargs):
                return "RSA/SHA256, Sun Feb  7 18:35:40 2016, Key ID" \
                       " 73bde98381b46521"

        hdr = PkgObjHdr()

    @staticmethod
    def create_pkg_obj(name, version="", release="", arch="", packager="",
                       from_repo=""):
        class DumbObj(object):
            pass

        obj = TestPkgHandler.TestPkgObj()
        obj.yumdb_info = DumbObj()
        obj.name = name
        obj.packager = None

        if version:
            obj.version = version
            obj.v = version
        if release:
            obj.release = release
            obj.r = release
        if version and release:
            obj.evr = version + "-" + release
        if arch:
            obj.arch = arch
        if packager:
            obj.packager = packager
        if from_repo:
            obj.yumdb_info.from_repo = from_repo
        return obj

    class GetInstalledPkgsWFingerprintsMocked(unit_tests.MockFunction):
        def prepare_test_pkg_tuples_w_fingerprints(self):
            class PkgData:
                def __init__(self, pkg_obj, fingerprint):
                    self.pkg_obj = pkg_obj
                    self.fingerprint = fingerprint

            obj1 = TestPkgHandler.create_pkg_obj("pkg1")
            obj2 = TestPkgHandler.create_pkg_obj("pkg2")
            obj3 = TestPkgHandler.create_pkg_obj("gpg-pubkey")
            pkgs = [PkgData(obj1, "199e2f91fd431d51"),  # RHEL
                    PkgData(obj2, "72f97b74ec551f03"),  # OL
                    PkgData(obj3, "199e2f91fd431d51")]  # RHEL
            return pkgs

        def __call__(self, *args, **kwargs):
            return self.prepare_test_pkg_tuples_w_fingerprints()

    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_fingerprints",
                     GetInstalledPkgsWFingerprintsMocked())
    def test_get_installed_pkgs_by_fingerprint_correct_fingerprint(self):
        pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint(
            "199e2f91fd431d51")

        self.assertEqual(pkgs_by_fingerprint, ["pkg1", "gpg-pubkey"])

    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_fingerprints",
                     GetInstalledPkgsWFingerprintsMocked())
    def test_get_installed_pkgs_by_fingerprint_incorrect_fingerprint(self):
        pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint(
            "non-existing fingerprint")

        self.assertEqual(pkgs_by_fingerprint, [])

    class GetInstalledPkgObjectsMocked(unit_tests.MockFunction):
        def __call__(self, name=""):
            if name and name != "installed_pkg":
                return []
            pkg_obj = TestPkgHandler.create_pkg_obj("installed_pkg", "0.1",
                                                    "1", "x86_64", 295,
                                                    "Oracle")
            return [pkg_obj]

    @unit_tests.mock(pkghandler, "get_installed_pkg_objects", GetInstalledPkgObjectsMocked())
    @unit_tests.mock(pkghandler, "get_pkg_fingerprint", lambda pkg: "some_fingerprint")
    def test_get_installed_pkgs_w_fingerprints(self):
        pkgs = pkghandler.get_installed_pkgs_w_fingerprints()

        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].pkg_obj.name, "installed_pkg")
        self.assertEqual(pkgs[0].fingerprint, "some_fingerprint")

        pkgs = pkghandler.get_installed_pkgs_w_fingerprints("non_existing")

        self.assertEqual(len(pkgs), 0)

    @unit_tests.mock(pkghandler, "get_rpm_header", lambda pkg: TestPkgHandler.TestPkgObj.PkgObjHdr())
    def test_get_pkg_fingerprint(self):
        pkg = TestPkgHandler.create_pkg_obj("pkg")

        fingerprint = pkghandler.get_pkg_fingerprint(pkg)

        self.assertEqual(fingerprint, "73bde98381b46521")

    class LogMocked(unit_tests.MockFunction):
        def __init__(self):
            self.msg = ""

        def __call__(self, msg):
            self.msg += "%s\n" % msg

    class TransactionSetMocked(unit_tests.MockFunction):
        def __call__(self):
            return self

        def dbMatch(self, key='name', value=''):
            db = [{rpm.RPMTAG_NAME: "pkg1",
                   rpm.RPMTAG_VERSION: "1",
                   rpm.RPMTAG_RELEASE: "2",
                   rpm.RPMTAG_EVR: "1-2"},
                  {rpm.RPMTAG_NAME: "pkg2",
                   rpm.RPMTAG_VERSION: "2",
                   rpm.RPMTAG_RELEASE: "3",
                   rpm.RPMTAG_EVR: "2-3"}]
            if key != 'name': # everything else than 'name' is unsupported ATM :)
                return []
            if not value:
                return db
            else:
                return [db_entry for db_entry in db if db_entry[rpm.RPMTAG_NAME] == value]

    @unit_tests.mock(logger.CustomLogger, "warning", LogMocked())
    @unit_tests.mock(rpm, "TransactionSet", TransactionSetMocked())
    def test_get_rpm_header(self):
        pkg = TestPkgHandler.create_pkg_obj("pkg1", "1", "2")
        hdr = pkghandler.get_rpm_header(pkg)
        self.assertEqual(hdr, {rpm.RPMTAG_NAME: "pkg1",
                               rpm.RPMTAG_VERSION: "1",
                               rpm.RPMTAG_RELEASE: "2",
                               rpm.RPMTAG_EVR: "1-2"})

        unknown_pkg = TestPkgHandler.create_pkg_obj("unknown", "1", "1")
        self.assertRaises(SystemExit, pkghandler.get_rpm_header, unknown_pkg)

    class ReturnPackagesMocked(unit_tests.MockFunction):
        def __call__(self, patterns=None):
            if patterns is None:
                patterns = []
            if patterns and patterns != ["installed_pkg"]:
                return []
            pkg_obj = TestPkgHandler.TestPkgObj()
            pkg_obj.name = "installed_pkg"
            return [pkg_obj]

    class QueryMocked(unit_tests.MockFunction):
        def __init__(self):
            self.filter_called = 0
            self.installed_called = 0
            self.stop_iteration = False
            self.pkg_obj = None

        def __call__(self, *args):
            self._setup_pkg()
            return self

        def __iter__(self):  # pylint: disable=non-iterator-returned
            return self

        def __next__(self):
            if self.stop_iteration or not self.pkg_obj:
                self.stop_iteration = False
                raise StopIteration
            self.stop_iteration = True
            return self.pkg_obj

        def _setup_pkg(self):
            self.pkg_obj = TestPkgHandler.TestPkgObj()
            self.pkg_obj.name = "installed_pkg"

        def filterm(self, empty):
            # Called internally in DNF when calling fill_sack - ignore, not needed
            pass

        def installed(self):
            self.installed_called += 1
            return self

        def filter(self, name__glob):
            self.filter_called += 1
            if name__glob and name__glob == "installed_pkg":
                self._setup_pkg()
            elif name__glob:
                self.pkg_obj = None
            return self

    try:
        @unit_tests.mock(pkgmanager.rpmsack.RPMDBPackageSack, "returnPackages",
                         ReturnPackagesMocked())
        def test_get_installed_pkg_objects_yum(self):
            self.get_installed_pkg_objects()
    except AttributeError:
        @unit_tests.mock(pkgmanager.query, "Query", QueryMocked())
        def test_get_installed_pkg_objects_dnf(self):
            self.get_installed_pkg_objects()

    def get_installed_pkg_objects(self):
        pkgs = pkghandler.get_installed_pkg_objects()

        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].name, "installed_pkg")

        pkgs = pkghandler.get_installed_pkg_objects("installed_pkg")

        self.assertEqual(len(pkgs), 1)
        self.assertEqual(pkgs[0].name, "installed_pkg")

        pkgs = pkghandler.get_installed_pkg_objects("non_existing")

        self.assertEqual(len(pkgs), 0)

    class PrintPkgInfoMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.pkgs = []

        def __call__(self, pkgs):
            self.called += 1
            self.pkgs = pkgs

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    @unit_tests.mock(system_info, "fingerprints_orig_os",
                     ["24c6a8a7f4a80eb5", "a963bbdbf533f4fa"])
    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_fingerprints",
                     GetInstalledPkgsWFingerprintsMocked())
    def test_get_third_party_pkgs(self):
        # This test covers also get_installed_pkgs_w_different_fingerprint
        pkgs = pkghandler.get_third_party_pkgs()

        self.assertEqual(pkghandler.print_pkg_info.called, 0)
        self.assertEqual(len(pkgs), 1)

        system_info.fingerprints_orig_os = ["72f97b74ec551f03"]
        pkghandler.print_pkg_info.called = 0

        pkghandler.get_third_party_pkgs()

        self.assertEqual(pkghandler.print_pkg_info.called, 0)

    @staticmethod
    def prepare_pkg_obj_for_print():
        obj1 = TestPkgHandler.create_pkg_obj("pkg1", "0.1", "1", "x86_64",
                                             "Oracle", "anaconda")
        obj2 = TestPkgHandler.create_pkg_obj("pkg2", "0.1", "1", "x86_64")
        obj3 = TestPkgHandler.create_pkg_obj("gpg-pubkey", "0.1", "1",
                                             "x86_64", from_repo="test")
        return [obj1, obj2, obj3]

    def test_print_pkg_info(self):
        # This test covers also get_pkg_nvra
        pkgs = TestPkgHandler.prepare_pkg_obj_for_print()
        result = pkghandler.print_pkg_info(pkgs)
        self.assertTrue(re.search(r"^Package\s+Packager\s+Repository$",
                                  result, re.MULTILINE))
        self.assertTrue(re.search(r"^pkg1-0\.1-1\.x86_64\s+Oracle\s+anaconda$",
                                  result, re.MULTILINE))
        self.assertTrue(re.search(r"^pkg2-0\.1-1\.x86_64\s+N/A\s+N/A$",
                                  result, re.MULTILINE))
        self.assertTrue(re.search(r"^gpg-pubkey-0\.1-1\.x86_64\s+N/A\s+test$",
                                  result, re.MULTILINE))

    @unit_tests.mock(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_fingerprints",
                     GetInstalledPkgsWFingerprintsMocked())
    def test_list_non_red_hat_pkgs_left(self):
        pkghandler.list_non_red_hat_pkgs_left()

        self.assertEqual(len(pkghandler.print_pkg_info.pkgs), 1)
        self.assertEqual(pkghandler.print_pkg_info.pkgs[0].name, "pkg2")

    class RemovePkgsMocked(unit_tests.MockFunction):
        def __init__(self):
            self.pkgs = None
            self.should_bkp = False

        def __call__(self, pkgs_to_remove, should_backup=False):
            self.pkgs = pkgs_to_remove
            self.should_bkp = should_backup

    @unit_tests.mock(system_info, "excluded_pkgs", ["installed_pkg",
                                                    "not_installed_pkg"])
    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(pkghandler, "print_pkg_info", DumbCallableObject())
    @unit_tests.mock(utils, "remove_pkgs", RemovePkgsMocked())
    @unit_tests.mock(pkghandler, "get_installed_pkg_objects",
                     GetInstalledPkgObjectsMocked())
    def test_remove_excluded_pkgs(self):
        pkghandler.remove_excluded_pkgs()

        self.assertEqual(len(utils.remove_pkgs.pkgs), 1)
        self.assertEqual(utils.remove_pkgs.pkgs[0], "installed_pkg-0.1-1.x86_64")

    class CallYumCmdWDowngradesMocked(unit_tests.MockFunction):
        def __init__(self):
            self.cmd = ""

        def __call__(self, cmd, fingerprints):
            self.cmd += "%s\n" % cmd

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(system_info, "fingerprints_orig_os", ["24c6a8a7f4a80eb5"])
    @unit_tests.mock(pkghandler, "call_yum_cmd_w_downgrades",
                     CallYumCmdWDowngradesMocked())
    def test_replace_non_red_hat_packages_distrosync(self):
        pkghandler.replace_non_red_hat_packages()

        output = "update\nreinstall\ndistro-sync\n"
        self.assertTrue(pkghandler.call_yum_cmd_w_downgrades.cmd ==
                        output)

    class InstallRhelKernelMocked(unit_tests.MockFunction):

        def __call__(self):
            return True

    class IsRHELKernelInstalledMocked(unit_tests.MockFunction):
        def __call__(self):
            return False

    @unit_tests.mock(pkghandler, "install_rhel_kernel", InstallRhelKernelMocked())
    @unit_tests.mock(pkghandler, "is_rhel_kernel_installed", IsRHELKernelInstalledMocked())
    def test_preserve_only_rhel_kernel_rhel_not_installed(self):
        self.assertRaises(SystemExit, pkghandler.preserve_only_rhel_kernel)

    @unit_tests.mock(pkghandler, "install_rhel_kernel", InstallRhelKernelMocked())
    @unit_tests.mock(pkghandler, "remove_non_rhel_kernels", DumbCallableObject())
    @unit_tests.mock(pkghandler, "install_gpg_keys", DumbCallableObject())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint",
                     GetInstalledPkgsWithFingerprintMocked(data=['kernel']))
    def test_preserve_only_rhel_kernel(self):
        pkghandler.preserve_only_rhel_kernel()

        self.assertEqual(utils.run_subprocess.cmd, "yum update -y kernel")
        self.assertEqual(pkghandler.get_installed_pkgs_by_fingerprint.called, 1)

    gpg_keys_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                 "..", "data", "version-independent"))

    @unit_tests.mock(utils, "DATA_DIR", gpg_keys_dir)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_install_gpg_keys(self):
        pkghandler.install_gpg_keys()

        gpg_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                "../data/version-independent/gpg-keys/*"))
        gpg_keys = glob.glob(gpg_dir)

        self.assertNotEqual(len(gpg_keys), 0)
        for gpg_key in gpg_keys:
            self.assertIn(
                'rpm --import %s' % os.path.join(gpg_dir, gpg_key),
                utils.run_subprocess.cmds)

    class GetInstalledPkgsWDifferentFingerprintMocked(
        unit_tests.MockFunction):
        def __init__(self):
            self.is_only_rhel_kernel_installed = False

        def __call__(self, *args, **kwargs):
            if self.is_only_rhel_kernel_installed:
                return []  # No third-party kernel
            else:
                return [
                    TestPkgHandler.create_pkg_obj(
                        "kernel", "0.1", "1", "x86_64", 295, "Oracle"),
                    TestPkgHandler.create_pkg_obj(
                        "kernel-uek", "0.1", "1", "x86_64", 295, "Oracle"),
                    TestPkgHandler.create_pkg_obj(
                        "kernel-headers", "0.1", "1", "x86_64", 295, "Oracle"),
                    TestPkgHandler.create_pkg_obj(
                        "kernel-uek-headers", "0.1", "1", "x86_64", 295, "Oracle"),
                    TestPkgHandler.create_pkg_obj(
                        "kernel-firmware", "0.1", "1", "x86_64", 295, "Oracle"),
                    TestPkgHandler.create_pkg_obj(
                        "kernel-uek-firmware", "0.1", "1", "x86_64", 295, "Oracle")
                ]

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(pkghandler, "handle_no_newer_rhel_kernel_available",
                     DumbCallableObject())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_different_fingerprint",
                     GetInstalledPkgsWDifferentFingerprintMocked())
    def test_install_rhel_kernel(self):
        # 1st scenario: kernels collide; the installed one is already RHEL
        # kernel = no action.
        utils.run_subprocess.output = "Package kernel-4.7.4-200.fc24" \
                                      " already installed, skipping."
        pkghandler.get_installed_pkgs_w_different_fingerprint \
            .is_only_rhel_kernel_installed = True

        update_kernel = pkghandler.install_rhel_kernel()

        self.assertFalse(update_kernel)

        # 2nd scenario: kernels collide; the installed one is from third party
        # = older-version RHEL kernel is to be installed.
        pkghandler.get_installed_pkgs_w_different_fingerprint \
            .is_only_rhel_kernel_installed = False

        update_kernel = pkghandler.install_rhel_kernel()

        self.assertTrue(update_kernel)

        # 3rd scenario: kernels do not collide; the RHEL one gets installed.
        utils.run_subprocess.output = "Installed:\nkernel"

        update_kernel = pkghandler.install_rhel_kernel()

        self.assertFalse(update_kernel)

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_get_kernel_availability(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_AVAILABLE
        installed, available = pkghandler.get_kernel_availability()
        self.assertEqual(installed, ['4.7.4-200.fc24'])
        self.assertEqual(available, ['4.5.5-300.fc24', '4.7.2-201.fc24', '4.7.4-200.fc24'])

        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE
        installed, available = pkghandler.get_kernel_availability()
        self.assertEqual(installed, ['4.7.4-200.fc24'])
        self.assertEqual(available, ['4.7.4-200.fc24'])

        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED
        installed, available = pkghandler.get_kernel_availability()
        self.assertEqual(installed, ['4.7.2-201.fc24', '4.7.4-200.fc24'])
        self.assertEqual(available, ['4.7.4-200.fc24'])

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_handle_older_rhel_kernel_available(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_AVAILABLE

        pkghandler.handle_no_newer_rhel_kernel_available()

        self.assertEqual(utils.run_subprocess.cmd, "yum install -y kernel-4.7.2-201.fc24")

    class ReplaceNonRhelInstalledKernelMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.version = None

        def __call__(self, version):
            self.called += 1
            self.version = version

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(pkghandler,
                     "replace_non_rhel_installed_kernel",
                     ReplaceNonRhelInstalledKernelMocked())
    def test_handle_older_rhel_kernel_not_available(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE

        pkghandler.handle_no_newer_rhel_kernel_available()

        self.assertEqual(pkghandler.replace_non_rhel_installed_kernel.called, 1)

    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(utils, "remove_pkgs", RemovePkgsMocked())
    def test_handle_older_rhel_kernel_not_available_multiple_installed(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED

        pkghandler.handle_no_newer_rhel_kernel_available()

        self.assertEqual(len(utils.remove_pkgs.pkgs), 1)
        self.assertEqual(utils.remove_pkgs.pkgs[0], "kernel-4.7.4-200.fc24")
        self.assertEqual(utils.run_subprocess.cmd, "yum install -y kernel-4.7.4-200.fc24")

    class DownloadPkgMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.pkg = None
            self.dest = None
            self.disablerepo = []
            self.enablerepo = []

        def __call__(self, pkg, dest, disablerepo, enablerepo):
            self.called += 1
            self.pkg = pkg
            self.dest = dest
            self.disablerepo = dest
            self.enablerepo = dest
            return 0

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(utils, "download_pkg", DownloadPkgMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_replace_non_rhel_installed_kernel(self):
        version = '4.7.4-200.fc24'
        pkghandler.replace_non_rhel_installed_kernel(version)
        self.assertEqual(utils.download_pkg.called, 1)
        self.assertEqual(utils.download_pkg.pkg, "kernel-4.7.4-200.fc24")
        self.assertEqual(utils.run_subprocess.cmd,
                         "rpm -i --force --replacepkgs %skernel-4.7.4-200.fc24*" % utils.TMP_DIR)

    def test_get_kernel(self):
        kernel_version = list(pkghandler.get_kernel(
            YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE))

        self.assertEqual(kernel_version, ["4.7.4-200.fc24", "4.7.4-200.fc24"])

    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_different_fingerprint",
                     GetInstalledPkgsWDifferentFingerprintMocked())
    @unit_tests.mock(pkghandler, "print_pkg_info", DumbCallableObject())
    @unit_tests.mock(utils, "remove_pkgs", RemovePkgsMocked())
    def test_remove_non_rhel_kernels(self):
        removed_pkgs = pkghandler.remove_non_rhel_kernels()

        self.assertEqual(len(removed_pkgs), 6)
        self.assertEqual([p.name for p in removed_pkgs], ["kernel",
                                                          "kernel-uek",
                                                          "kernel-headers",
                                                          "kernel-uek-headers",
                                                          "kernel-firmware",
                                                          "kernel-uek-firmware"])

    @unit_tests.mock(pkghandler, "get_installed_pkgs_w_different_fingerprint",
                     GetInstalledPkgsWDifferentFingerprintMocked())
    @unit_tests.mock(pkghandler, "print_pkg_info", DumbCallableObject())
    @unit_tests.mock(utils, "remove_pkgs", RemovePkgsMocked())
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_install_additional_rhel_kernel_pkgs(self):
        removed_pkgs = pkghandler.remove_non_rhel_kernels()
        pkghandler.install_additional_rhel_kernel_pkgs(removed_pkgs)
        self.assertEqual(pkghandler.call_yum_cmd.called, 2)

    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint",
                     GetInstalledPkgsWithFingerprintMocked(data=['kernel']))
    def test_check_installed_rhel_kernel_returns_true(self):
        self.assertEqual(pkghandler.is_rhel_kernel_installed(), True)

    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint",
                     GetInstalledPkgsWithFingerprintMocked(data=[]))
    def test_check_installed_rhel_kernel_returns_false(self):
        self.assertEqual(pkghandler.is_rhel_kernel_installed(), False)

    @unit_tests.mock(pkghandler, "get_third_party_pkgs", lambda: [])
    @unit_tests.mock(logger.CustomLogger, "info", LogMocked())
    def test_list_third_party_pkgs_no_pkgs(self):
        pkghandler.list_third_party_pkgs()

        self.assertEqual(logger.CustomLogger.info.msg, "No third party packages installed.\n")

    @unit_tests.mock(pkghandler, "get_third_party_pkgs", GetInstalledPkgsWFingerprintsMocked())
    @unit_tests.mock(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    @unit_tests.mock(logger.CustomLogger, "warning", LogMocked())
    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    def test_list_third_party_pkgs(self):
        pkghandler.list_third_party_pkgs()

        self.assertEqual(len(pkghandler.print_pkg_info.pkgs), 3)
        self.assertTrue("Only packages signed by" in logger.CustomLogger.warning.msg)


YUM_PROTECTED_ERROR = """Error: Trying to remove "systemd", which is protected
Error: Trying to remove "yum", which is protected"""

YUM_REQUIRES_ERROR = """Error: Package: libreport-anaconda-2.1.11-30.el7.x86_64 (rhel-7-server-rpms)
           Requires: libreport-plugin-rhtsupport = 2.1.11-30.el7
           Available: libreport-plugin-rhtsupport-2.1.11-10.el7.x86_64 (rhel-7-server-rpms)
               libreport-plugin-rhtsupport = 2.1.11-10.el7
           Installing: libreport-plugin-rhtsupport-2.1.11-23.el7_1.x86_64 (rhel-7-server-rpms)
               libreport-plugin-rhtsupport = 2.1.11-23.el7_1
Error: Package: abrt-cli-2.1.11-34.el7.x86_64 (rhel-7-server-rpms)
           Requires: libreport-plugin-rhtsupport >= 2.1.11-28
           Available: libreport-plugin-rhtsupport-2.1.11-10.el7.x86_64 (rhel-7-server-rpms)
               libreport-plugin-rhtsupport = 2.1.11-10.el7
           Installing: libreport-plugin-rhtsupport-2.1.11-21.el7.x86_64 (rhel-7-server-rpms)
               libreport-plugin-rhtsupport = 2.1.11-21.el7"""

YUM_MULTILIB_ERROR = """
Error: Protected multilib versions: 2:p11-kit-0.18.7-1.fc19.i686 != p11-kit-0.18.3-1.fc19.x86_64
Error: Protected multilib versions: openldap-2.4.36-4.fc19.i686 != openldap-2.4.35-4.fc19.x86_64"""

# The following yum error is currently not being handled by the tool. The
# tool would somehow need to decide, which of the two packages to remove and
# ask the user to confirm the removal.
YUM_FILE_CONFLICT_ERROR = """Transaction Check Error:
  file /lib/firmware/ql2500_fw.bin from install of ql2500-firmware-7.03.00-1.el6_5.noarch conflicts with file from package linux-firmware-20140911-0.1.git365e80c.0.8.el6.noarch
  file /lib/firmware/ql2400_fw.bin from install of ql2400-firmware-7.03.00-1.el6_5.noarch conflicts with file from package linux-firmware-20140911-0.1.git365e80c.0.8.el6.noarch
  file /lib/firmware/phanfw.bin from install of netxen-firmware-4.0.534-3.1.el6.noarch conflicts with file from package linux-firmware-20140911-0.1.git365e80c.0.8.el6.noarch"""  # pylint: disable=C0301

YUM_KERNEL_LIST_OLDER_AVAILABLE = """Installed Packages
kernel.x86_64    4.7.4-200.fc24   @updates
Available Packages
kernel.x86_64    4.5.5-300.fc24   fedora
kernel.x86_64    4.7.2-201.fc24   @updates
kernel.x86_64    4.7.4-200.fc24   @updates"""

YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE = """Installed Packages
kernel.x86_64    4.7.4-200.fc24   @updates
Available Packages
kernel.x86_64    4.7.4-200.fc24   @updates"""

YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED = """Installed Packages
kernel.x86_64    4.7.2-201.fc24   @updates
kernel.x86_64    4.7.4-200.fc24   @updates
Available Packages
kernel.x86_64    4.7.4-200.fc24   @updates"""
