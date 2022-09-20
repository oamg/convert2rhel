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
import logging
import os
import re
import sys

from collections import namedtuple

import pytest
import rpm
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import backup, pkghandler, pkgmanager, unit_tests, utils  # Imports unit_tests/__init__.py
from convert2rhel.pkghandler import (
    _get_packages_to_update_dnf,
    _get_packages_to_update_yum,
    get_total_packages_to_update,
)
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import GetLoggerMocked, is_rpm_based_os, run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import TestPkgObj, all_systems, centos8, create_pkg_obj


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
            self.args = None

        def __call__(self, command, args, *other_args, **kwargs):
            if self.fail_once and self.called == 0:
                self.return_code = 1
            if self.fail_once and self.called > 0:
                self.return_code = 0
            self.called += 1
            self.command = command
            self.args = args
            return self.return_string, self.return_code

    class GetInstalledPkgsByFingerprintMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return ["pkg1", "pkg2"]

    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output_text="Test output"):
            self.cmd = []
            self.cmds = []
            self.called = 0
            self.output = output_text
            self.ret_code = 0

        def __call__(self, cmd, print_cmd=True, print_output=True):
            self.cmd = cmd
            self.cmds.append(cmd)
            self.called += 1
            return self.output, self.ret_code

    class IsFileMocked(unit_tests.MockFunction):
        def __init__(self, is_file):
            self.is_file = is_file

        def __call__(self, *args, **kwargs):
            return self.is_file

    class DumbCallableObject(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1
            return

    class CommandCallableObject(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.command = None

        def __call__(self, command):
            self.called += 1
            self.command = command
            return

    class SysExitCallableObject(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            sys.exit(1)

    class GetSizeMocked(unit_tests.MockFunction):
        def __init__(self, file_size):
            self.file_size = file_size

        def __call__(self, *args, **kwargs):
            return self.file_size

    class StoreContentToFileMocked(unit_tests.MockFunction):
        def __init__(self):
            self.content = ""
            self.filename = ""
            self.called = 0

        def __call__(self, filename, content):
            self.content = content
            self.filename = filename
            self.called += 1

    class RemovePkgsMocked(unit_tests.MockFunction):
        def __init__(self):
            self.pkgs = None
            self.should_bkp = False
            self.critical = False

        def __call__(self, pkgs_to_remove, backup=False, critical=False):
            self.pkgs = pkgs_to_remove
            self.should_bkp = backup
            self.critical = critical

    @unit_tests.mock(pkghandler, "loggerinst", GetLoggerMocked())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=False))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=0))
    def test_clear_versionlock_plugin_not_enabled(self):
        self.assertFalse(pkghandler.clear_versionlock())
        self.assertEqual(len(pkghandler.loggerinst.info_msgs), 1)
        self.assertEqual(
            pkghandler.loggerinst.info_msgs,
            ["Usage of YUM/DNF versionlock plugin not detected."],
        )

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=True))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=1))
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    @unit_tests.mock(backup.RestorableFile, "backup", DumbCallableObject)
    @unit_tests.mock(backup.RestorableFile, "restore", DumbCallableObject)
    def test_clear_versionlock_user_says_yes(self):
        pkghandler.clear_versionlock()
        self.assertEqual(pkghandler.call_yum_cmd.called, 1)
        self.assertEqual(pkghandler.call_yum_cmd.command, "versionlock")
        self.assertEqual(pkghandler.call_yum_cmd.args, ["clear"])

    @unit_tests.mock(utils, "ask_to_continue", SysExitCallableObject())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=True))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=1))
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_clear_versionlock_user_says_no(self):
        self.assertRaises(SystemExit, pkghandler.clear_versionlock)
        self.assertEqual(pkghandler.call_yum_cmd.called, 0)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(8, 0))
    @unit_tests.mock(system_info, "releasever", "8")
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_call_yum_cmd(self):
        pkghandler.call_yum_cmd("install")

        self.assertEqual(
            utils.run_subprocess.cmd,
            [
                "yum",
                "install",
                "-y",
                "--releasever=8",
                "--setopt=module_platform_id=platform:el8",
            ],
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", "7Server")
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_call_yum_cmd_not_setting_releasever(self):
        pkghandler.call_yum_cmd("install", set_releasever=False)

        self.assertEqual(utils.run_subprocess.cmd, ["yum", "install", "-y"])

    @pytest.mark.skipif(
        not is_rpm_based_os(),
        reason="Current test runs only on rpm based systems.",
    )
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_call_yum_cmd_w_downgrades_continuous_fail(self):
        pkghandler.call_yum_cmd.return_code = 1

        self.assertRaises(
            SystemExit,
            pkghandler.call_yum_cmd_w_downgrades,
            "test_cmd",
            ["pkg"],
        )
        self.assertEqual(pkghandler.call_yum_cmd.called, pkghandler.MAX_YUM_CMD_CALLS)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(tool_opts, "no_rhsm", True)
    @unit_tests.mock(tool_opts, "disablerepo", ["*"])
    @unit_tests.mock(tool_opts, "enablerepo", ["rhel-7-extras-rpm"])
    def test_call_yum_cmd_with_disablerepo_and_enablerepo(self):
        pkghandler.call_yum_cmd("install")

        self.assertEqual(
            utils.run_subprocess.cmd,
            [
                "yum",
                "install",
                "-y",
                "--disablerepo=*",
                "--enablerepo=rhel-7-extras-rpm",
            ],
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(system_info, "submgr_enabled_repos", ["rhel-7-extras-rpm"])
    @unit_tests.mock(tool_opts, "enablerepo", ["not-to-be-used-in-the-yum-call"])
    def test_call_yum_cmd_with_submgr_enabled_repos(self):
        pkghandler.call_yum_cmd("install")

        self.assertEqual(
            utils.run_subprocess.cmd,
            ["yum", "install", "-y", "--enablerepo=rhel-7-extras-rpm"],
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(system_info, "submgr_enabled_repos", ["not-to-be-used-in-the-yum-call"])
    @unit_tests.mock(tool_opts, "enablerepo", ["not-to-be-used-in-the-yum-call"])
    def test_call_yum_cmd_with_repo_overrides(self):
        pkghandler.call_yum_cmd("install", ["pkg"], enable_repos=[], disable_repos=[])

        self.assertEqual(utils.run_subprocess.cmd, ["yum", "install", "-y", "pkg"])

        pkghandler.call_yum_cmd(
            "install",
            ["pkg"],
            enable_repos=["enable-repo"],
            disable_repos=["disable-repo"],
        )

        self.assertEqual(
            utils.run_subprocess.cmd,
            [
                "yum",
                "install",
                "-y",
                "--disablerepo=disable-repo",
                "--enablerepo=enable-repo",
                "pkg",
            ],
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_call_yum_cmd_w_downgrades_correct_cmd(self):
        pkghandler.call_yum_cmd_w_downgrades("update", ["pkg1", "pkg2"])

        self.assertEqual(utils.run_subprocess.cmd, ["yum", "update", "-y", "pkg1", "pkg2"])

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_call_yum_cmd_w_downgrades_one_fail(self):
        pkghandler.call_yum_cmd.fail_once = True

        pkghandler.call_yum_cmd_w_downgrades("test_cmd", ["pkg"])

        self.assertEqual(pkghandler.call_yum_cmd.called, 2)

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint", lambda _: ["pkg"])
    @unit_tests.mock(pkghandler, "resolve_dep_errors", lambda output: output)
    @unit_tests.mock(
        pkghandler,
        "get_problematic_pkgs",
        lambda pkg: {"errors": set([pkg]), "mismatches": set()},
    )
    @unit_tests.mock(pkghandler, "remove_pkgs", RemovePkgsMocked())
    def test_call_yum_cmd_w_downgrades_remove_problematic_pkgs(self):
        pkghandler.call_yum_cmd.return_code = 1
        pkghandler.MAX_YUM_CMD_CALLS = 1

        self.assertRaises(
            SystemExit,
            pkghandler.call_yum_cmd_w_downgrades,
            "test_cmd",
            ["fingerprint"],
        )

        self.assertIn(pkghandler.call_yum_cmd.return_string, pkghandler.remove_pkgs.pkgs)
        self.assertEqual(pkghandler.remove_pkgs.critical, False)

    def test_get_pkgs_to_distro_sync(self):
        problematic_pkgs = {
            "protected": set(["a"]),
            "errors": set(["b"]),
            "multilib": set(["c", "a"]),
            "required": set(["d", "a"]),
            "mismatches": set(["e", "a"]),
        }
        all_pkgs = pkghandler.get_pkgs_to_distro_sync(problematic_pkgs)
        self.assertEqual(
            all_pkgs,
            problematic_pkgs["errors"]
            | problematic_pkgs["protected"]
            | problematic_pkgs["multilib"]
            | problematic_pkgs["required"],
        )

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_resolve_dep_errors_one_downgrade_fixes_the_error(self):
        pkghandler.call_yum_cmd.fail_once = True

        pkghandler.resolve_dep_errors(YUM_PROTECTED_ERROR, set())

        self.assertEqual(pkghandler.call_yum_cmd.called, 1)

    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_resolve_dep_errors_unable_to_fix_by_downgrades(self):
        pkghandler.call_yum_cmd.return_code = 1
        pkghandler.call_yum_cmd.return_string = YUM_MULTILIB_ERROR

        pkghandler.resolve_dep_errors(YUM_PROTECTED_ERROR, set())

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
        pkghandler.resolve_dep_errors("No info about problematic pkgs.", set())

        self.assertEqual(pkghandler.call_yum_cmd.called, 0)

    class GetInstalledPkgsWFingerprintsMocked(unit_tests.MockFunction):
        def prepare_test_pkg_tuples_w_fingerprints(self):
            class PkgData:
                def __init__(self, pkg_obj, fingerprint):
                    self.pkg_obj = pkg_obj
                    self.fingerprint = fingerprint

            obj1 = create_pkg_obj("pkg1")
            obj2 = create_pkg_obj("pkg2")
            obj3 = create_pkg_obj("gpg-pubkey")
            pkgs = [
                PkgData(obj1, "199e2f91fd431d51"),  # RHEL
                PkgData(obj2, "72f97b74ec551f03"),  # OL
                PkgData(obj3, "199e2f91fd431d51"),
            ]  # RHEL
            return pkgs

        def __call__(self, *args, **kwargs):
            return self.prepare_test_pkg_tuples_w_fingerprints()

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_fingerprints",
        GetInstalledPkgsWFingerprintsMocked(),
    )
    def test_get_installed_pkgs_by_fingerprint_correct_fingerprint(self):
        pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint("199e2f91fd431d51")

        self.assertEqual(pkgs_by_fingerprint, ["pkg1", "gpg-pubkey"])

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_fingerprints",
        GetInstalledPkgsWFingerprintsMocked(),
    )
    def test_get_installed_pkgs_by_fingerprint_incorrect_fingerprint(self):
        pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint("non-existing fingerprint")

        self.assertEqual(pkgs_by_fingerprint, [])

    class GetInstalledPkgObjectsMocked(unit_tests.MockFunction):
        def __call__(self, name=""):
            if name and name != "installed_pkg":
                return []
            pkg_obj = create_pkg_obj(
                name="installed_pkg",
                version="0.1",
                release="1",
                arch="x86_64",
                packager="Oracle",
                from_repo="repoid",
            )
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

    @unit_tests.mock(
        pkghandler,
        "get_rpm_header",
        lambda pkg: TestPkgObj.PkgObjHdr(),
    )
    def test_get_pkg_fingerprint(self):
        pkg = create_pkg_obj("pkg")

        fingerprint = pkghandler.get_pkg_fingerprint(pkg)

        self.assertEqual(fingerprint, "73bde98381b46521")

    class TransactionSetMocked(unit_tests.MockFunction):
        def __call__(self):
            return self

        def dbMatch(self, key="name", value=""):
            db = [
                {
                    rpm.RPMTAG_NAME: "pkg1",
                    rpm.RPMTAG_VERSION: "1",
                    rpm.RPMTAG_RELEASE: "2",
                    rpm.RPMTAG_EVR: "1-2",
                },
                {
                    rpm.RPMTAG_NAME: "pkg2",
                    rpm.RPMTAG_VERSION: "2",
                    rpm.RPMTAG_RELEASE: "3",
                    rpm.RPMTAG_EVR: "2-3",
                },
            ]
            if key != "name":  # everything else than 'name' is unsupported ATM :)
                return []
            if not value:
                return db
            else:
                return [db_entry for db_entry in db if db_entry[rpm.RPMTAG_NAME] == value]

    @unit_tests.mock(logging.Logger, "warning", GetLoggerMocked())
    @unit_tests.mock(rpm, "TransactionSet", TransactionSetMocked())
    @pytest.mark.skipif(
        not is_rpm_based_os(),
        reason="Current test runs only on rpm based systems.",
    )
    def test_get_rpm_header(self):
        pkg = create_pkg_obj(name="pkg1", version="1", release="2")
        hdr = pkghandler.get_rpm_header(pkg)
        self.assertEqual(
            hdr,
            {
                rpm.RPMTAG_NAME: "pkg1",
                rpm.RPMTAG_VERSION: "1",
                rpm.RPMTAG_RELEASE: "2",
                rpm.RPMTAG_EVR: "1-2",
            },
        )
        unknown_pkg = create_pkg_obj(name="unknown", version="1", release="1")
        self.assertRaises(SystemExit, pkghandler.get_rpm_header, unknown_pkg)

    class ReturnPackagesMocked(unit_tests.MockFunction):
        def __call__(self, patterns=None):
            if patterns is None:
                patterns = []
            if patterns and patterns != ["installed_pkg"]:
                return []
            pkg_obj = TestPkgObj()
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
            self.pkg_obj = TestPkgObj()
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

    if hasattr(pkgmanager, "rpmsack"):

        @unit_tests.mock(
            pkgmanager.rpmsack.RPMDBPackageSack,
            "returnPackages",
            ReturnPackagesMocked(),
        )
        def test_get_installed_pkg_objects_yum(self):
            self.get_installed_pkg_objects()

    elif hasattr(pkgmanager, "query"):

        @unit_tests.mock(pkgmanager.query, "Query", QueryMocked())
        def test_get_installed_pkg_objects_dnf(self):
            self.get_installed_pkg_objects()

    else:
        assert not is_rpm_based_os()

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
    @unit_tests.mock(
        system_info,
        "fingerprints_orig_os",
        ["24c6a8a7f4a80eb5", "a963bbdbf533f4fa"],
    )
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_fingerprints",
        GetInstalledPkgsWFingerprintsMocked(),
    )
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
    def prepare_pkg_obj_for_print_with_yum():
        obj1 = create_pkg_obj(
            name="pkg1",
            version="0.1",
            release="1",
            arch="x86_64",
            packager="Oracle",
            from_repo="anaconda",
        )
        obj2 = create_pkg_obj(name="pkg2", epoch=1, version="0.1", release="1", arch="x86_64")
        obj3 = create_pkg_obj(
            name="gpg-pubkey",
            version="0.1",
            release="1",
            arch="x86_64",
            from_repo="test",
        )
        return [obj1, obj2, obj3]

    @unit_tests.mock(pkgmanager, "TYPE", "yum")
    def test_print_pkg_info_yum(self):
        pkgs = TestPkgHandler.prepare_pkg_obj_for_print_with_yum()
        result = pkghandler.print_pkg_info(pkgs)
        self.assertTrue(
            re.search(
                r"^Package\s+Vendor/Packager\s+Repository$",
                result,
                re.MULTILINE,
            )
        )
        self.assertTrue(
            re.search(
                r"^pkg1-0\.1-1\.x86_64\s+Oracle\s+anaconda$",
                result,
                re.MULTILINE,
            )
        )
        self.assertTrue(re.search(r"^pkg2-0\.1-1\.x86_64\s+N/A\s+N/A$", result, re.MULTILINE))
        self.assertTrue(
            re.search(
                r"^gpg-pubkey-0\.1-1\.x86_64\s+N/A\s+test$",
                result,
                re.MULTILINE,
            )
        )

    @staticmethod
    def prepare_pkg_obj_for_print_with_dnf():
        obj1 = create_pkg_obj(
            name="pkg1",
            version="0.1",
            release="1",
            arch="x86_64",
            vendor="Oracle",
            from_repo="anaconda",
            manager="dnf",
        )
        obj2 = create_pkg_obj(
            name="pkg2",
            epoch=1,
            version="0.1",
            release="1",
            arch="x86_64",
            manager="dnf",
        )
        obj3 = create_pkg_obj(
            name="gpg-pubkey",
            version="0.1",
            release="1",
            arch="x86_64",
            from_repo="test",
            manager="dnf",
        )
        return [obj1, obj2, obj3]

    def test_get_vendor(self):
        pkg_with_vendor = create_pkg_obj(
            name="pkg1",
            version="0.1",
            release="1",
            arch="x86_64",
            vendor="Oracle",
            from_repo="anaconda",
            manager="dnf",
        )
        pkg_with_packager = create_pkg_obj(
            name="pkg1",
            version="0.1",
            release="1",
            arch="x86_64",
            packager="Oracle",
            from_repo="anaconda",
            manager="dnf",
        )
        self.assertTrue(pkghandler.get_vendor(pkg_with_vendor), "Oracle")
        self.assertTrue(pkghandler.get_vendor(pkg_with_packager), "N/A")

    @unit_tests.mock(pkgmanager, "TYPE", "dnf")
    def test_print_pkg_info_dnf(self):
        pkgs = TestPkgHandler.prepare_pkg_obj_for_print_with_dnf()
        result = pkghandler.print_pkg_info(pkgs)
        self.assertTrue(
            re.search(
                r"^pkg1-0\.1-1\.x86_64\s+Oracle\s+anaconda$",
                result,
                re.MULTILINE,
            )
        )
        self.assertTrue(re.search(r"^pkg2-0\.1-1\.x86_64\s+N/A\s+@@System$", result, re.MULTILINE))
        self.assertTrue(
            re.search(
                r"^gpg-pubkey-0\.1-1\.x86_64\s+N/A\s+test$",
                result,
                re.MULTILINE,
            )
        )

    @unit_tests.mock(pkgmanager, "TYPE", "dnf")
    def test_get_pkg_nevra(self):
        obj = create_pkg_obj(name="pkg", epoch=1, version="2", release="3", arch="x86_64")
        # The DNF style is the default
        self.assertEqual(pkghandler.get_pkg_nevra(obj), "pkg-1:2-3.x86_64")

        pkgmanager.TYPE = "yum"
        self.assertEqual(pkghandler.get_pkg_nevra(obj), "1:pkg-2-3.x86_64")

    @unit_tests.mock(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_fingerprints",
        GetInstalledPkgsWFingerprintsMocked(),
    )
    def test_list_non_red_hat_pkgs_left(self):
        pkghandler.list_non_red_hat_pkgs_left()

        self.assertEqual(len(pkghandler.print_pkg_info.pkgs), 1)
        self.assertEqual(pkghandler.print_pkg_info.pkgs[0].name, "pkg2")

    @unit_tests.mock(system_info, "excluded_pkgs", ["installed_pkg", "not_installed_pkg"])
    @unit_tests.mock(pkghandler, "remove_pkgs_with_confirm", CommandCallableObject())
    def test_remove_excluded_pkgs(self):
        pkghandler.remove_excluded_pkgs()

        self.assertEqual(pkghandler.remove_pkgs_with_confirm.called, 1)
        self.assertEqual(
            pkghandler.remove_pkgs_with_confirm.command,
            system_info.excluded_pkgs,
        )

    @unit_tests.mock(system_info, "repofile_pkgs", ["installed_pkg", "not_installed_pkg"])
    @unit_tests.mock(pkghandler, "remove_pkgs_with_confirm", CommandCallableObject())
    def test_remove_repofile_pkgs(self):
        pkghandler.remove_repofile_pkgs()

        self.assertEqual(pkghandler.remove_pkgs_with_confirm.called, 1)
        self.assertEqual(
            pkghandler.remove_pkgs_with_confirm.command,
            system_info.repofile_pkgs,
        )

    class GetInstalledPkgObjectsWDiffFingerprintMocked(unit_tests.MockFunction):
        def __call__(self, fingerprints, name=""):
            if name and name != "installed_pkg":
                return []
            if "rhel_fingerprint" in fingerprints:
                pkg_obj = create_pkg_obj(
                    name="installed_pkg",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Oracle",
                    from_repo="repoid",
                )
            else:
                pkg_obj = create_pkg_obj(
                    name="installed_pkg",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Red Hat",
                    from_repo="repoid",
                )
            return [pkg_obj]

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(pkghandler, "print_pkg_info", DumbCallableObject())
    @unit_tests.mock(system_info, "fingerprints_rhel", ["rhel_fingerprint"])
    @unit_tests.mock(pkghandler, "remove_pkgs", RemovePkgsMocked())
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgObjectsWDiffFingerprintMocked(),
    )
    def test_remove_pkgs_with_confirm(self):
        pkghandler.remove_pkgs_with_confirm(["installed_pkg", "not_installed_pkg"])

        self.assertEqual(len(pkghandler.remove_pkgs.pkgs), 1)
        self.assertEqual(pkghandler.remove_pkgs.pkgs[0], "installed_pkg-0.1-1.x86_64")

    class CallYumCmdWDowngradesMocked(unit_tests.MockFunction):
        def __init__(self):
            self.cmd = ""
            self.pkgs = []

        def __call__(self, cmd, pkgs):
            self.cmd += "%s\n" % cmd
            self.pkgs += [pkgs]

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint", lambda x: ["pkg"])
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(pkghandler, "call_yum_cmd_w_downgrades", CallYumCmdWDowngradesMocked())
    def test_replace_non_red_hat_packages_distrosync_execution_order(self):
        pkghandler.replace_non_red_hat_packages()

        output = "update\nreinstall\ndistro-sync\n"
        self.assertTrue(pkghandler.call_yum_cmd_w_downgrades.cmd == output)

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint", lambda x: ["pkg"])
    @unit_tests.mock(system_info, "id", "oracle")
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(6, 0))
    @unit_tests.mock(pkghandler, "call_yum_cmd_w_downgrades", CallYumCmdWDowngradesMocked())
    def test_replace_non_red_hat_packages_distrosync_on_ol6(self):
        pkghandler.replace_non_red_hat_packages()

        for i in range(0, 3):
            self.assertEqual(
                ["pkg", "subscription-manager*"],
                pkghandler.call_yum_cmd_w_downgrades.pkgs[i],
            )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(pkghandler, "install_rhel_kernel", lambda: True)
    @unit_tests.mock(pkghandler, "fix_invalid_grub2_entries", lambda: None)
    @unit_tests.mock(pkghandler, "remove_non_rhel_kernels", DumbCallableObject())
    @unit_tests.mock(pkghandler, "install_gpg_keys", DumbCallableObject())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_by_fingerprint",
        GetInstalledPkgsWithFingerprintMocked(data=["kernel"]),
    )
    @unit_tests.mock(system_info, "name", "CentOS7")
    @unit_tests.mock(system_info, "arch", "x86_64")
    @unit_tests.mock(utils, "store_content_to_file", StoreContentToFileMocked())
    def test_preserve_only_rhel_kernel(self):
        pkghandler.preserve_only_rhel_kernel()

        self.assertEqual(utils.run_subprocess.cmd, ["yum", "update", "-y", "kernel"])
        self.assertEqual(pkghandler.get_installed_pkgs_by_fingerprint.called, 1)

    gpg_keys_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "data", "version-independent"))

    @unit_tests.mock(utils, "DATA_DIR", gpg_keys_dir)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_install_gpg_keys(self):
        pkghandler.install_gpg_keys()

        gpg_dir = os.path.realpath(
            os.path.join(
                os.path.dirname(__file__),
                "../data/version-independent/gpg-keys/*",
            )
        )
        gpg_keys = glob.glob(gpg_dir)

        self.assertNotEqual(len(gpg_keys), 0)
        for gpg_key in gpg_keys:
            self.assertIn(
                ["rpm", "--import", os.path.join(gpg_dir, gpg_key)],
                utils.run_subprocess.cmds,
            )

    class GetInstalledPkgsWDifferentFingerprintMocked(unit_tests.MockFunction):
        def __init__(self):
            self.is_only_rhel_kernel_installed = False
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1
            if self.is_only_rhel_kernel_installed:
                return []  # No third-party kernel
            else:
                return [
                    create_pkg_obj(
                        name="kernel",
                        version="3.10.0",
                        release="1127.19.1.el7",
                        arch="x86_64",
                        packager="Oracle",
                    ),
                    create_pkg_obj(
                        name="kernel-uek",
                        version="0.1",
                        release="1",
                        arch="x86_64",
                        packager="Oracle",
                        from_repo="repoid",
                    ),
                    create_pkg_obj(
                        name="kernel-headers",
                        version="0.1",
                        release="1",
                        arch="x86_64",
                        packager="Oracle",
                        from_repo="repoid",
                    ),
                    create_pkg_obj(
                        name="kernel-uek-headers",
                        version="0.1",
                        release="1",
                        arch="x86_64",
                        packager="Oracle",
                        from_repo="repoid",
                    ),
                    create_pkg_obj(
                        name="kernel-firmware",
                        version="0.1",
                        release="1",
                        arch="x86_64",
                        packager="Oracle",
                        from_repo="repoid",
                    ),
                    create_pkg_obj(
                        name="kernel-uek-firmware",
                        version="0.1",
                        release="1",
                        arch="x86_64",
                        packager="Oracle",
                        from_repo="repoid",
                    ),
                ]

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(
        pkghandler,
        "handle_no_newer_rhel_kernel_available",
        DumbCallableObject(),
    )
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(),
    )
    def test_install_rhel_kernel(self):
        # 1st scenario: kernels collide; the installed one is already a RHEL kernel = no action.
        utils.run_subprocess.output = "Package kernel-3.10.0-1127.19.1.el7.x86_64 already installed and latest version"
        pkghandler.get_installed_pkgs_w_different_fingerprint.is_only_rhel_kernel_installed = True

        update_kernel = pkghandler.install_rhel_kernel()

        self.assertFalse(update_kernel)

        # 2nd scenario: kernels collide; the installed one is from third party
        # = older-version RHEL kernel is to be installed.
        pkghandler.get_installed_pkgs_w_different_fingerprint.is_only_rhel_kernel_installed = False

        update_kernel = pkghandler.install_rhel_kernel()

        self.assertTrue(update_kernel)

        # 3rd scenario: kernels do not collide; the RHEL one gets installed.
        utils.run_subprocess.output = "Installed:\nkernel"

        update_kernel = pkghandler.install_rhel_kernel()

        self.assertFalse(update_kernel)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(),
    )
    def test_install_rhel_kernel_already_installed_regexp(self):
        # RHEL 6 and 7
        utils.run_subprocess.output = "Package kernel-2.6.32-754.33.1.el6.x86_64 already installed and latest version"

        pkghandler.install_rhel_kernel()

        self.assertEqual(pkghandler.get_installed_pkgs_w_different_fingerprint.called, 1)

        # RHEL 8
        utils.run_subprocess.output = "Package kernel-4.18.0-193.el8.x86_64 is already installed."

        pkghandler.install_rhel_kernel()

        self.assertEqual(pkghandler.get_installed_pkgs_w_different_fingerprint.called, 2)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_get_kernel_availability(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_AVAILABLE
        installed, available = pkghandler.get_kernel_availability()
        self.assertEqual(installed, ["4.7.4-200.fc24"])
        self.assertEqual(available, ["4.5.5-300.fc24", "4.7.2-201.fc24", "4.7.4-200.fc24"])

        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE
        installed, available = pkghandler.get_kernel_availability()
        self.assertEqual(installed, ["4.7.4-200.fc24"])
        self.assertEqual(available, ["4.7.4-200.fc24"])

        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED
        installed, available = pkghandler.get_kernel_availability()
        self.assertEqual(installed, ["4.7.2-201.fc24", "4.7.4-200.fc24"])
        self.assertEqual(available, ["4.7.4-200.fc24"])

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_handle_older_rhel_kernel_available(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_AVAILABLE

        pkghandler.handle_no_newer_rhel_kernel_available()

        self.assertEqual(
            utils.run_subprocess.cmd,
            ["yum", "install", "-y", "kernel-4.7.2-201.fc24"],
        )

    class ReplaceNonRhelInstalledKernelMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.version = None

        def __call__(self, version):
            self.called += 1
            self.version = version

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(
        pkghandler,
        "replace_non_rhel_installed_kernel",
        ReplaceNonRhelInstalledKernelMocked(),
    )
    def test_handle_older_rhel_kernel_not_available(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE

        pkghandler.handle_no_newer_rhel_kernel_available()

        self.assertEqual(pkghandler.replace_non_rhel_installed_kernel.called, 1)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "releasever", None)
    @unit_tests.mock(backup, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    @unit_tests.mock(pkghandler, "remove_pkgs", RemovePkgsMocked())
    def test_handle_older_rhel_kernel_not_available_multiple_installed(self):
        utils.run_subprocess.output = YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED

        pkghandler.handle_no_newer_rhel_kernel_available()

        self.assertEqual(len(pkghandler.remove_pkgs.pkgs), 1)
        self.assertEqual(pkghandler.remove_pkgs.pkgs[0], "kernel-4.7.4-200.fc24")
        self.assertEqual(
            utils.run_subprocess.cmd,
            ["yum", "install", "-y", "kernel-4.7.4-200.fc24"],
        )
        self.assertEqual(len(pkghandler.remove_pkgs.pkgs), 1)
        self.assertEqual(pkghandler.remove_pkgs.pkgs[0], "kernel-4.7.4-200.fc24")
        self.assertEqual(utils.run_subprocess.cmd, ["yum", "install", "-y", "kernel-4.7.4-200.fc24"])

    class DownloadPkgMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.pkg = None
            self.dest = None
            self.enable_repos = []
            self.disable_repos = []
            self.to_return = "/path/to.rpm"

        def __call__(self, pkg, dest, enable_repos, disable_repos):
            self.called += 1
            self.pkg = pkg
            self.dest = dest
            self.enable_repos = enable_repos
            self.disable_repos = disable_repos
            return self.to_return

    @unit_tests.mock(system_info, "submgr_enabled_repos", ["enabled_rhsm_repo"])
    @unit_tests.mock(tool_opts, "enablerepo", [])  # to be changed later in the test
    @unit_tests.mock(tool_opts, "no_rhsm", False)  # to be changed later in the test
    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(utils, "download_pkg", DownloadPkgMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_replace_non_rhel_installed_kernel(self):
        # test the use case where RHSM is used for the conversion
        version = "4.7.4-200.fc24"
        pkghandler.replace_non_rhel_installed_kernel(version)
        self.assertEqual(utils.download_pkg.called, 1)
        self.assertEqual(utils.download_pkg.pkg, "kernel-4.7.4-200.fc24")
        self.assertEqual(utils.download_pkg.enable_repos, ["enabled_rhsm_repo"])
        self.assertEqual(
            utils.run_subprocess.cmd,
            [
                "rpm",
                "-i",
                "--force",
                "--nodeps",
                "--replacepkgs",
                "%skernel-4.7.4-200.fc24*" % utils.TMP_DIR,
            ],
        )

        # test the use case where custom repos are used for the conversion
        system_info.submgr_enabled_repos = []
        tool_opts.no_rhsm = True
        tool_opts.enablerepo = ["custom_repo"]
        pkghandler.replace_non_rhel_installed_kernel(version)
        self.assertEqual(utils.download_pkg.enable_repos, ["custom_repo"])

    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    @unit_tests.mock(utils, "download_pkg", DownloadPkgMocked())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_replace_non_rhel_installed_kernel_failing(self):
        # First, test utility exiting when unable to download the kernel
        utils.download_pkg.to_return = None
        version = "4.7.4-200.fc24"
        self.assertRaises(SystemExit, pkghandler.replace_non_rhel_installed_kernel, version)

        # Second, test utility exiting when unable to replace the kernel
        utils.download_pkg.to_return = "/path/to.rpm"
        utils.run_subprocess.ret_code = 1
        version = "4.7.4-200.fc24"
        self.assertRaises(SystemExit, pkghandler.replace_non_rhel_installed_kernel, version)

    def test_get_kernel(self):
        kernel_version = list(pkghandler.get_kernel(YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE))

        self.assertEqual(kernel_version, ["4.7.4-200.fc24", "4.7.4-200.fc24"])

    @unit_tests.mock(pkghandler, "is_rhel_kernel_installed", lambda: True)
    def test_verify_rhel_kernel_installed(self):
        pkghandler.verify_rhel_kernel_installed()

    @unit_tests.mock(pkghandler, "is_rhel_kernel_installed", lambda: False)
    def test_verify_rhel_kernel_installed_not_installed(self):
        self.assertRaises(SystemExit, pkghandler.verify_rhel_kernel_installed)

    @unit_tests.mock(pkghandler, "get_installed_pkgs_by_fingerprint", lambda x, name: [])
    def test_is_rhel_kernel_installed_no(self):
        self.assertFalse(pkghandler.is_rhel_kernel_installed())

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_by_fingerprint",
        lambda x, name: ["kernel"],
    )
    def test_is_rhel_kernel_installed_yes(self):
        self.assertTrue(pkghandler.is_rhel_kernel_installed())

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(),
    )
    @unit_tests.mock(pkghandler, "print_pkg_info", DumbCallableObject())
    @unit_tests.mock(pkghandler, "remove_pkgs", RemovePkgsMocked())
    def test_remove_non_rhel_kernels(self):
        removed_pkgs = pkghandler.remove_non_rhel_kernels()

        self.assertEqual(len(removed_pkgs), 6)
        self.assertEqual(
            [p.name for p in removed_pkgs],
            [
                "kernel",
                "kernel-uek",
                "kernel-headers",
                "kernel-uek-headers",
                "kernel-firmware",
                "kernel-uek-firmware",
            ],
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(system_info, "arch", "x86_64")
    @unit_tests.mock(pkghandler.logging, "getLogger", GetLoggerMocked())
    def test_fix_invalid_grub2_entries_not_applicable(self):
        pkghandler.fix_invalid_grub2_entries()
        self.assertFalse(len(pkghandler.logging.getLogger.info_msgs), 1)

        system_info.version = namedtuple("Version", ["major", "minor"])(8, 0)
        system_info.arch = "s390x"
        pkghandler.fix_invalid_grub2_entries()
        self.assertFalse(len(pkghandler.logging.getLogger.info_msgs), 1)

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(8, 0))
    @unit_tests.mock(system_info, "arch", "x86_64")
    @unit_tests.mock(
        utils,
        "get_file_content",
        lambda x: "1b11755afe1341d7a86383ca4944c324\n",
    )
    @unit_tests.mock(
        glob,
        "glob",
        lambda x: [
            "/boot/loader/entries/1b11755afe1341d7a86383ca4944c324-0-rescue.conf",
            "/boot/loader/entries/1b11755afe1341d7a86383ca4944c324-4.18.0-193.28.1.el8_2.x86_64.conf",
            "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-0-rescue.conf",
            "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-4.18.0-193.el8.x86_64.conf",
            "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-5.4.17-2011.7.4.el8uek.x86_64.conf",
        ],
    )
    @unit_tests.mock(os, "remove", DumbCallableObject())
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_fix_invalid_grub2_entries(self):
        pkghandler.fix_invalid_grub2_entries()

        self.assertEqual(os.remove.called, 3)
        self.assertEqual(utils.run_subprocess.called, 2)

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(),
    )
    @unit_tests.mock(pkghandler, "print_pkg_info", DumbCallableObject())
    @unit_tests.mock(pkghandler, "remove_pkgs", RemovePkgsMocked())
    @unit_tests.mock(pkghandler, "call_yum_cmd", CallYumCmdMocked())
    def test_install_additional_rhel_kernel_pkgs(self):
        removed_pkgs = pkghandler.remove_non_rhel_kernels()
        pkghandler.install_additional_rhel_kernel_pkgs(removed_pkgs)
        self.assertEqual(pkghandler.call_yum_cmd.called, 2)

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_by_fingerprint",
        GetInstalledPkgsWithFingerprintMocked(data=["kernel"]),
    )
    def test_check_installed_rhel_kernel_returns_true(self):
        self.assertEqual(pkghandler.is_rhel_kernel_installed(), True)

    @unit_tests.mock(
        pkghandler,
        "get_installed_pkgs_by_fingerprint",
        GetInstalledPkgsWithFingerprintMocked(data=[]),
    )
    def test_check_installed_rhel_kernel_returns_false(self):
        self.assertEqual(pkghandler.is_rhel_kernel_installed(), False)

    @unit_tests.mock(pkghandler, "get_third_party_pkgs", lambda: [])
    @unit_tests.mock(pkghandler, "loggerinst", GetLoggerMocked())
    def test_list_third_party_pkgs_no_pkgs(self):
        pkghandler.list_third_party_pkgs()

        self.assertTrue("No third party packages installed" in pkghandler.loggerinst.info_msgs[0])

    @unit_tests.mock(
        pkghandler,
        "get_third_party_pkgs",
        GetInstalledPkgsWFingerprintsMocked(),
    )
    @unit_tests.mock(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    @unit_tests.mock(pkghandler, "loggerinst", GetLoggerMocked())
    @unit_tests.mock(utils, "ask_to_continue", DumbCallableObject())
    def test_list_third_party_pkgs(self):
        pkghandler.list_third_party_pkgs()

        self.assertEqual(len(pkghandler.print_pkg_info.pkgs), 3)
        self.assertTrue("Only packages signed by" in pkghandler.loggerinst.warning_msgs[0])

    @unit_tests.mock(tool_opts, "disablerepo", ["*", "rhel-7-extras-rpm"])
    @unit_tests.mock(tool_opts, "enablerepo", ["rhel-7-extras-rpm"])
    @unit_tests.mock(pkghandler, "loggerinst", GetLoggerMocked())
    def test_is_disable_and_enable_repos_has_same_repo(self):
        pkghandler.has_duplicate_repos_across_disablerepo_enablerepo_options()
        self.assertTrue("Duplicate repositories were found" in pkghandler.loggerinst.warning_msgs[0])

    @unit_tests.mock(tool_opts, "disablerepo", ["*"])
    @unit_tests.mock(tool_opts, "enablerepo", ["rhel-7-extras-rpm"])
    @unit_tests.mock(pkghandler.logging, "getLogger", GetLoggerMocked())
    def test_is_disable_and_enable_repos_doesnt_thas_same_repo(self):
        pkghandler.has_duplicate_repos_across_disablerepo_enablerepo_options()
        self.assertEqual(len(pkghandler.logging.getLogger.warning_msgs), 0)

    @unit_tests.mock(system_info, "name", "Oracle Linux Server release 7.9")
    @unit_tests.mock(system_info, "arch", "x86_64")
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 9))
    @unit_tests.mock(pkghandler.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(
        utils,
        "get_file_content",
        lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=kernel-uek\n",
    )
    @unit_tests.mock(utils, "store_content_to_file", StoreContentToFileMocked())
    def test_fix_default_kernel_converting_oracle(self):
        pkghandler.fix_default_kernel()
        self.assertTrue(len(pkghandler.logging.getLogger.info_msgs), 1)
        self.assertTrue(len(pkghandler.logging.getLogger.warning_msgs), 1)
        self.assertTrue(
            "Detected leftover boot kernel, changing to RHEL kernel" in pkghandler.logging.getLogger.warning_msgs[0]
        )
        self.assertTrue("/etc/sysconfig/kernel", utils.store_content_to_file.filename)
        self.assertTrue("DEFAULTKERNEL=kernel" in utils.store_content_to_file.content)
        self.assertFalse("DEFAULTKERNEL=kernel-uek" in utils.store_content_to_file.content)
        self.assertFalse("DEFAULTKERNEL=kernel-core" in utils.store_content_to_file.content)

        system_info.name = "Oracle Linux Server release 8.1"
        system_info.version = namedtuple("Version", ["major", "minor"])(8, 1)
        pkghandler.fix_default_kernel()
        self.assertTrue(len(pkghandler.logging.getLogger.info_msgs), 1)
        self.assertTrue(len(pkghandler.logging.getLogger.warning_msgs), 1)
        self.assertTrue(
            "Detected leftover boot kernel, changing to RHEL kernel" in pkghandler.logging.getLogger.warning_msgs[0]
        )
        self.assertTrue("DEFAULTKERNEL=kernel" in utils.store_content_to_file.content)
        self.assertFalse("DEFAULTKERNEL=kernel-uek" in utils.store_content_to_file.content)

    @unit_tests.mock(system_info, "name", "CentOS Plus Linux Server release 7.9")
    @unit_tests.mock(system_info, "arch", "x86_64")
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 9))
    @unit_tests.mock(pkghandler.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(
        utils,
        "get_file_content",
        lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=kernel-plus\n",
    )
    @unit_tests.mock(utils, "store_content_to_file", StoreContentToFileMocked())
    def test_fix_default_kernel_converting_centos_plus(self):
        pkghandler.fix_default_kernel()
        self.assertTrue(len(pkghandler.logging.getLogger.info_msgs), 1)
        self.assertTrue(len(pkghandler.logging.getLogger.warning_msgs), 1)
        self.assertTrue("/etc/sysconfig/kernel", utils.store_content_to_file.filename)
        self.assertTrue("DEFAULTKERNEL=kernel" in utils.store_content_to_file.content)
        self.assertFalse("DEFAULTKERNEL=kernel-plus" in utils.store_content_to_file.content)

    @unit_tests.mock(system_info, "name", "CentOS Plus Linux Server release 7.9")
    @unit_tests.mock(system_info, "arch", "x86_64")
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 9))
    @unit_tests.mock(pkghandler.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(
        utils,
        "get_file_content",
        lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=kernel\n",
    )
    @unit_tests.mock(utils, "store_content_to_file", StoreContentToFileMocked())
    def test_fix_default_kernel_with_no_incorrect_kernel(self):
        pkghandler.fix_default_kernel()
        self.assertTrue(len(pkghandler.logging.getLogger.info_msgs), 2)
        self.assertTrue(any("Boot kernel validated." in message for message in pkghandler.logging.getLogger.debug_msgs))
        self.assertTrue(len(pkghandler.logging.getLogger.warning_msgs) == 0)


@pytest.mark.parametrize(
    ("retcode", "output"),
    (
        (
            1,
            "Updating Subscription Management repositories.\n"
            "Repository rhel-8-for-x86_64-baseos-rpms is listed more than once in the configuration\n"
            "Repository rhel-8-for-x86_64-appstream-rpms is listed more than once in the configuration\n"
            "Last metadata expiration check: 0:12:45 ago on Wed 01 Sep 2021 01:57:50 PM UTC.\n"
            "No package vlc installed.\nError: No packages marked for distribution synchronization.\n",
        ),
        (
            0,
            "Updating Subscription Management repositories.\n"
            "Repository rhel-8-for-x86_64-baseos-rpms is listed more than once in the configuration\n"
            "Repository rhel-8-for-x86_64-appstream-rpms is listed more than once in the configuration\n"
            "Last metadata expiration check: 0:15:23 ago on Mon 06 Sep 2021 08:27:13 AM UTC.\n"
            "No package cpaste installed.\nDependencies resolved.\nNothing to do.\nComplete!\n",
        ),
    ),
)
def test_call_yum_cmd_w_downgrades(monkeypatch, retcode, output):
    monkeypatch.setattr(
        pkghandler,
        "call_yum_cmd",
        value=mock.Mock(return_value=(output, retcode)),
    )
    resolve_dep_errors = mock.Mock()
    monkeypatch.setattr(pkghandler, "resolve_dep_errors", value=resolve_dep_errors)
    monkeypatch.setattr(pkghandler, "get_problematic_pkgs", value=mock.Mock())

    pkghandler.call_yum_cmd_w_downgrades("anything", ["anything"])

    resolve_dep_errors.assert_not_called()


@pytest.mark.parametrize(
    ("version1", "version2", "expected"),
    (
        ("123-4.fc35", "123-4.fc35", 0),
        ("123-5.fc35", "123-4.fc35", 1),
        ("123-3.fc35", "123-4.fc35", -1),
        (
            "4.6~pre16262021g84ef6bd9-3.fc35",
            "4.6~pre16262021g84ef6bd9-3.fc35",
            0,
        ),
        ("2:8.2.3568-1.fc35", "2:8.2.3568-1.fc35", 0),
    ),
)
def test_compare_package_versions(version1, version2, expected):
    assert pkghandler.compare_package_versions(version1, version2) == expected


@pytest.mark.parametrize(
    ("package_manager_type", "packages", "expected", "reposdir"),
    (
        (
            "yum",
            [
                "convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
                "convert2rhel.src-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
            ],
            frozenset(
                (
                    "convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
                    "convert2rhel.src-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
                )
            ),
            None,
        ),
        (
            "yum",
            [
                "convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
                "convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
            ],
            frozenset(("convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",)),
            None,
        ),
        (
            "dnf",
            [
                "dunst-1.7.1-1.fc35.x86_64",
                "dunst-1.7.0-1.fc35.x86_64",
                "java-11-openjdk-headless-1:11.0.13.0.8-2.fc35.x86_64",
            ],
            frozenset(
                (
                    "dunst-1.7.1-1.fc35.x86_64",
                    "dunst-1.7.0-1.fc35.x86_64",
                    "java-11-openjdk-headless-1:11.0.13.0.8-2.fc35.x86_64",
                )
            ),
            None,
        ),
        (
            "dnf",
            [
                "dunst-1.7.1-1.fc35.x86_64",
                "dunst-1.7.0-1.fc35.x86_64",
                "java-11-openjdk-headless-1:11.0.13.0.8-2.fc35.x86_64",
            ],
            frozenset(
                (
                    "dunst-1.7.1-1.fc35.x86_64",
                    "dunst-1.7.0-1.fc35.x86_64",
                    "java-11-openjdk-headless-1:11.0.13.0.8-2.fc35.x86_64",
                )
            ),
            "test/reposdir",
        ),
        (
            "dnf",
            [
                "dunst-1.7.1-1.fc35.x86_64",
                "dunst-1.7.1-1.fc35.x86_64",
                "java-11-openjdk-headless-1:11.0.13.0.8-2.fc35.x86_64",
            ],
            frozenset(
                (
                    "dunst-1.7.1-1.fc35.x86_64",
                    "java-11-openjdk-headless-1:11.0.13.0.8-2.fc35.x86_64",
                )
            ),
            "test/reposdir",
        ),
    ),
)
@centos8
def test_get_total_packages_to_update(
    package_manager_type,
    packages,
    expected,
    reposdir,
    pretend_os,
    monkeypatch,
):
    monkeypatch.setattr(pkgmanager, "TYPE", package_manager_type)
    if package_manager_type == "dnf":
        monkeypatch.setattr(
            pkghandler,
            "_get_packages_to_update_%s" % package_manager_type,
            value=lambda reposdir: packages,
        )
    else:
        monkeypatch.setattr(
            pkghandler,
            "_get_packages_to_update_%s" % package_manager_type,
            value=lambda: packages,
        )
    assert get_total_packages_to_update(reposdir=reposdir) == expected


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
@pytest.mark.parametrize(("packages"), ((["package-1", "package-2", "package-3"],)))
def test_get_packages_to_update_yum(packages, monkeypatch):
    PkgName = namedtuple("PkgNames", ["name"])
    PkgUpdates = namedtuple("PkgUpdates", ["updates"])
    transaction_pkgs = []
    for package in packages:
        transaction_pkgs.append(PkgName(package))

    pkg_lists_mock = mock.Mock(return_value=PkgUpdates(transaction_pkgs))

    monkeypatch.setattr(pkgmanager.YumBase, "doPackageLists", value=pkg_lists_mock)

    assert _get_packages_to_update_yum() == packages


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
@pytest.mark.parametrize(
    ("packages", "reposdir"),
    (
        (
            ["package-1", "package-2", "package-i3"],
            None,
        ),
        (
            ["package-1"],
            "test/reposdir",
        ),
    ),
)
@all_systems
def test_get_packages_to_update_dnf(packages, reposdir, pretend_os, monkeypatch):
    dummy_mock = mock.Mock()
    PkgName = namedtuple("PkgNames", ["name"])
    transaction_pkgs = [PkgName(package) for package in packages]

    monkeypatch.setattr(pkgmanager.Base, "read_all_repos", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "fill_sack", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "upgrade_all", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "resolve", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "transaction", value=transaction_pkgs)

    assert _get_packages_to_update_dnf(reposdir=reposdir) == packages


YUM_PROTECTED_ERROR = """Error: Trying to remove "systemd", which is protected
Error: Trying to remove "yum", which is protected"""

YUM_REQUIRES_ERROR = """Error: Package: libreport-anaconda-2.1.11-30.el7.x86_64 (rhel-7-server-rpms)
           Requires: libreport-plugin-rhtsupport = 2.1.11-30.el7
           Available: libreport-plugin-rhtsupport-2.1.11-10.el7.x86_64 (rhel-7-server-rpms)
               libreport-plugin-rhtsupport = 2.1.11-10.el7
           Installing: libreport-plugin-rhtsupport-2.1.11-23.el7_1.x86_64 (rhel-7-server-rpms)
               libreport-plugin-rhtsupport = 2.1.11-23.el7_1
Error: Package: abrt-cli-2.1.11-34.el7.x86_64 (rhel-7-server-rpms)
           Requires: python2-hawkey >= 0.7.0
           Removing: python2-hawkey-0.22.5-2.el7_9.x86_64 (@extras/7)
               python2-hawkey = 0.22.5-2.el7_9
           Downgraded By: python2-hawkey-0.6.3-4.el7.x86_64 (rhel-7-server-rpms)
               python2-hawkey = 0.6.3-4.el7
Error: Package: redhat-lsb-trialuse-4.1-27.el7.centos.1.x86_64 (@base/7)
           Requires: redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1
           Removing: redhat-lsb-core-4.1-27.el7.centos.1.x86_64 (@base/7)
               redhat-lsb-core(x86-64) = 4.1-27.el7.centos.1
           Downgraded By: redhat-lsb-core-4.1-27.el7.x86_64 (rhel-7-server-rpms)
               redhat-lsb-core(x86-64) = 4.1-27.el7
           Available: redhat-lsb-core-4.1-24.el7.x86_64 (rhel-7-server-rpms)
               redhat-lsb-core(x86-64) = 4.1-24.el7
Error: Package: mod_ldap-2.1.11-34.el7.x86_64 (rhel-7-server-rpms)
           Requires: python2_hawkey >= 0.7.0
           Removing: python2_hawkey-0.22.5-2.el7_9.x86_64 (@extras/7)
               python2_hawkey = 0.22.5-2.el7_9
           Downgraded By: python2_hawkey-0.6.3-4.el7.x86_64 (rhel-7-server-rpms)
               python2_hawkey = 0.6.3-4.el7
Error: Package: gcc-c++-4.8.5-44.0.3.el7.x86_64 (@ol7_latest)
           Requires: gcc = 4.8.5-44.0.3.el7
           Removing: gcc-4.8.5-44.0.3.el7.x86_64 (@ol7_latest)
               gcc = 4.8.2-16.el7
               gcc = 4.8.5-44.0.3.el7
           Downgraded By: gcc-4.8.5-44.el7.x86_64 (rhel-7-server-rpms)
               gcc = 4.8.2-16.el7
               gcc = 4.8.5-44.el7
           Available: gcc-4.8.2-16.el7.x86_64 (rhel-7-server-rpms)
               gcc = 4.8.2-16.el7"""

# Test for bugs in parsing package names that have unusual features
# This is artificial test data; these packages don't normally dep on themselves
# but we want to test that both the code handling packages in error state and
# the code handling packages they require will catch these package names.
YUM_UNUSUAL_PKG_NAME_REQUIRES_ERROR = """
Error: Package: gcc-c++-4.8.5-44.0.3.el7.x86_64 (rhel-7-server-rpms)
           Requires: gcc-c++ = 4.8.5-44.0.3.el7
Error: Package: NetworkManager-1.18.8-2.0.1.el7_9.x86_64 (rhel-7-server-rpms)
           Requires: NetworkManager = 1.18.8-2.0.1.el7_9
Error: Package: ImageMagick-c++-6.9.10.68-6.el7_9.x86_64 (rhel-7-server-rpms)
           Requires: ImageMagick-c++ = 6.9.10.68-6.el7_9
Error: Package: devtoolset-11-libstdc++-devel-11.2.1-1.2.el7.x86_64 (rhel-7-server-rpms)
           Requires: devtoolset-11-libstdc++-devel = 11.2.1-1.2.el7
Error: Package: java-1.8.0-openjdk-1.8.0.312.b07-2.fc33.x86_64 (rhel-7-server-rpms)
           Requires: java-1.8.0-openjdk = 1.8.0.312.b07-2.fc33
Error: Package: 389-ds-base-1.3.10.2-14.el7_9.x86_64 (rhel-7-server-rpms)
           Requires: 389-ds-base = 1.3.10.2-14.el7_9
               """

YUM_MULTILIB_ERROR = """
       Protected multilib versions: libstdc++-4.8.5-44.el7.i686 != libstdc++-4.8.5-44.0.3.el7.x86_64
Error: Protected multilib versions: 2:p11-kit-0.18.7-1.fc19.i686 != p11-kit-0.18.3-1.fc19.x86_64
Error: Protected multilib versions: openldap-2.4.36-4.fc19.i686 != openldap-2.4.35-4.fc19.x86_64"""

YUM_MISMATCHED_PKGS_ERROR = """
Problem: cannot install both python39-psycopg2-2.8.6-2.module+el8.4.0+9822+20bf1249.x86_64 and python39-psycopg2-2.8.6-2.module_el8.4.0+680+7b309a77.x86_64
   - package python39-psycopg2-debug-2.8.6-2.module_el8.4.0+680+7b309a77.x86_64 requires python39-psycopg2 = 2.8.6-2.module_el8.4.0+680+7b309a77, but none of the providers can be installed
   - cannot install the best update candidate for package python39-psycopg2-2.8.6-2.module_el8.4.0+680+7b309a77.x86_64
   - problem with installed package python39-psycopg2-debug-2.8.6-2.module_el8.4.0+680+7b309a77.x86_64"""

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

with open(
    os.path.join(
        os.path.dirname(__file__),
        "data/pkghandler_yum_distro_sync_output_expect_deps_for_3_pkgs_found.txt",
    )
) as f:
    YUM_DISTRO_SYNC_OUTPUT = f.read()


@pytest.mark.parametrize(
    "yum_output, expected",
    (
        (
            "",
            {
                "protected": set(),
                "errors": set(),
                "multilib": set(),
                "required": set(),
                "mismatches": set(),
            },
        ),
        (
            YUM_PROTECTED_ERROR,
            {
                "protected": set(("systemd", "yum")),
                "errors": set(),
                "multilib": set(),
                "required": set(),
                "mismatches": set(),
            },
        ),
        (
            YUM_MULTILIB_ERROR,
            {
                "protected": set(),
                "errors": set(),
                "multilib": set(("libstdc++", "openldap", "p11-kit")),
                "required": set(),
                "mismatches": set(),
            },
        ),
        (
            YUM_MISMATCHED_PKGS_ERROR,
            {
                "protected": set(),
                "errors": set(),
                "multilib": set(),
                "required": set(),
                "mismatches": set(("python39-psycopg2-debug",)),
            },
        ),
        # These currently do not pass because the Requires handling
        # misparses a Requires in the test data (It turns
        # python2_hawkey into python2).  Testing it in its own function
        # for now.
        # (
        #     YUM_REQUIRES_ERROR,
        #     {
        #         "protected": set(),
        #         "errors": set(("gcc-c++", "libreport-anaconda", "abrt-cli", "mod_ldap", "redhat-lsb-trialuse")),
        #         "multilib": set(),
        #         "required": set(("gcc", "libreport-plugin-rhtsupport", "python2-hawkey", "redhat-lsb-core")),
        #         "mismatches": set(),
        #     },
        # ),
        # (
        #     YUM_UNUSUAL_PKG_NAME_REQUIRES_ERROR,
        #     {
        #         "protected": set(),
        #         "errors": set(("gcc-c++", "NetworkManager", "ImageMagick-c++",
        #         "devtoolset-11-libstdc++-devel", "java-1.8.0-openjdk", "389-ds-base")),
        #         "multilib": set(),
        #         "required": set(("gcc-c++", "NetworkManager", "ImageMagick-c++",
        #         "devtoolset-11-libstdc++-devel", "java-1.8.0-openjdk", "389-ds-base")),
        #         "mismatches": set(),
        #     },
        # ),
    ),
)
def test_get_problematic_pkgs(yum_output, expected):
    error_pkgs = pkghandler.get_problematic_pkgs(yum_output, set())

    assert error_pkgs == expected


# FIXME: There is a bug in requires handling.  We're detecting the python2
# package is a problem because there's a Requires: python2_hawkey line.  Until
# that's fixed, the following two test cases will test the things that work
# (Errors parsing).  Once it is fixed, re-implement this test via parametrize
# on test_get_problematic_pkgs instead of a standalone test case.
# https://github.com/oamg/convert2rhel/issues/378
def test_get_problematic_pkgs_requires():
    """Merge into test_get_problematic_pkgs once requires parsing bug is fixed."""
    error_pkgs = pkghandler.get_problematic_pkgs(YUM_REQUIRES_ERROR, set())
    assert "libreport-anaconda" in error_pkgs["errors"]
    assert "abrt-cli" in error_pkgs["errors"]
    assert "libreport-plugin-rhtsupport" in error_pkgs["required"]
    assert "python2-hawkey" in error_pkgs["required"]
    assert "mod_ldap" in error_pkgs["errors"]
    assert "redhat-lsb-trialuse" in error_pkgs["errors"]
    assert "redhat-lsb-core" in error_pkgs["required"]
    assert "gcc-c++" in error_pkgs["errors"]
    assert "gcc" in error_pkgs["required"]


def test_get_problematic_pkgs_requires_unusual_names():
    """Merge into test_get_problematic_pkgs once requires parsing bug is fixed."""
    error_pkgs = pkghandler.get_problematic_pkgs(YUM_UNUSUAL_PKG_NAME_REQUIRES_ERROR, set())
    assert "gcc-c++" in error_pkgs["errors"]
    assert "NetworkManager" in error_pkgs["errors"]
    assert "ImageMagick-c++" in error_pkgs["errors"]
    assert "devtoolset-11-libstdc++-devel" in error_pkgs["errors"]
    assert "java-1.8.0-openjdk" in error_pkgs["errors"]
    assert "389-ds-base" in error_pkgs["errors"]


@pytest.mark.parametrize(
    "output, message, expected_names",
    (
        # Test just the regex itself
        ("Test", "%s", set()),
        ("Error: Package: not_a_package_name", "%s", set()),
        ("gcc-10.3.1-1.el8.x86_64", "%s", set(["gcc"])),
        ("gcc-c++-10.3.1-1.el8.x86_64", "%s", set(["gcc-c++"])),
        (
            "ImageMagick-c++-6.9.10.68-6.el7_9.i686",
            "%s",
            set(["ImageMagick-c++"]),
        ),
        ("389-ds-base-1.3.10.2-14.el7_9.x86_64", "%s", set(["389-ds-base"])),
        (
            "devtoolset-11-libstdc++-devel-11.2.1-1.2.el7.x86_64",
            "%s",
            set(["devtoolset-11-libstdc++-devel"]),
        ),
        (
            "devtoolset-1.1-libstdc++-devel-11.2.1-1.2.el7.x86_64",
            "%s",
            set(["devtoolset-1.1-libstdc++-devel"]),
        ),
        (
            "java-1.8.0-openjdk-1.8.0.312.b07-2.fc33.x86_64",
            "%s",
            set(["java-1.8.0-openjdk"]),
        ),
        # Test NEVR with an epoch
        (
            "NetworkManager-1:1.18.8-2.0.1.el7_9.x86_64",
            "%s",
            set(["NetworkManager"]),
        ),
        # Test with simple error messages that we've pre-compiled the regex for
        (
            "Error: Package: gcc-10.3.1-1.el8.x86_64",
            "Error: Package: %s",
            set(["gcc"]),
        ),
        (
            "multilib versions: gcc-10.3.1-1.el8.i686",
            "multilib versions: %s",
            set(["gcc"]),
        ),
        (
            "problem with installed package: gcc-10.3.1-1.el8.x86_64",
            "problem with installed package: %s",
            set(["gcc"]),
        ),
        # Test that a template that was not pre-compiled works
        (
            """Some Test Junk
     Test gcc-1-2.i686""",
            "Test %s",
            set(["gcc"]),
        ),
        # Test with multiple packages to be found
        (
            """Junk
     Test gcc-1-2.i686
     Test gcc-c++-1-2.i686
     More Junk
     Test bash-3-4.x86_64""",
            "Test %s",
            set(["gcc", "gcc-c++", "bash"]),
        ),
        # Test with actual yum output
        (
            YUM_DISTRO_SYNC_OUTPUT,
            "Error: Package: %s",
            set(["gcc", "gcc-c++", "libstdc++-devel"]),
        ),
    ),
)
def test_find_pkg_names(output, message, expected_names):
    """Test that find_pkg_names finds the expected packages."""
    assert pkghandler.find_pkg_names(output, message) == expected_names


@pytest.mark.parametrize(
    "output, message",
    (
        # Test just the regex itself
        ("Test", "%s"),
        ("Error: Package: not_a_package_name", "%s"),
        # Test that the message key is having an influence
        ("multilib versions: gcc-10.3.1-1.el8.i686", "Error: Package: %s"),
    ),
)
def test_find_pkg_names_no_names(output, message):
    """Test that find_pkg_names does not find any names in these outputs."""
    assert pkghandler.find_pkg_names(output, message) == set()


@pytest.mark.parametrize(
    (
        "packages",
        "expected",
        "is_rpm_installed",
    ),
    (
        (["package1", "package2"], [], False),
        (["package1", "package2"], ["package1", "package2"], True),
    ),
)
def test_filter_installed_pkgs(packages, expected, is_rpm_installed, monkeypatch):
    monkeypatch.setattr(
        system_info,
        "is_rpm_installed",
        mock.Mock(return_value=is_rpm_installed),
    )
    assert pkghandler.filter_installed_pkgs(packages) == expected


@pytest.mark.parametrize(
    ("rpm_paths", "expected"),
    ((["pkg1", "pkg2"], ["pkg1", "pkg2"]),),
)
def test_get_pkg_names_from_rpm_paths(rpm_paths, expected, monkeypatch):
    monkeypatch.setattr(utils, "get_package_name_from_rpm", lambda x: x)
    assert pkghandler.get_pkg_names_from_rpm_paths(rpm_paths) == expected


@pytest.mark.parametrize(
    ("ret_code", "expected"), ((0, "Cached yum metadata cleaned successfully."), (1, "Failed to clean yum metadata"))
)
def test_clean_yum_metadata(ret_code, expected, monkeypatch, caplog):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (
                ("yum", "clean", "metadata", "--quiet"),
                (expected, ret_code),
            ),
        ),
    )
    monkeypatch.setattr(
        pkghandler.utils,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    pkghandler.clean_yum_metadata()
    assert expected in caplog.records[-1].message
