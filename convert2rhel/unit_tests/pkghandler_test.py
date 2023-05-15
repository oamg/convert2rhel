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

from convert2rhel import backup, pkghandler, pkgmanager, unit_tests, utils  # Imports unit_tests/__init__.py
from convert2rhel.pkghandler import (
    PackageInformation,
    PackageNevra,
    _get_packages_to_update_dnf,
    _get_packages_to_update_yum,
    get_total_packages_to_update,
)
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import (
    GetLoggerMocked,
    TestPkgObj,
    create_pkg_information,
    create_pkg_obj,
    is_rpm_based_os,
    mock_decorator,
)
from convert2rhel.unit_tests.conftest import all_systems, centos7, centos8
from convert2rhel.unit_tests.subscription_test import DumbCallable


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class CommandCallableObject(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0
        self.command = None

    def __call__(self, command):
        self.called += 1
        self.command = command
        return


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
                create_pkg_information(
                    name="kernel",
                    version="3.10.0",
                    release="1127.19.1.el7",
                    arch="x86_64",
                    packager="Oracle",
                ),
                create_pkg_information(
                    name="kernel-uek",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Oracle",
                ),
                create_pkg_information(
                    name="kernel-headers",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Oracle",
                ),
                create_pkg_information(
                    name="kernel-uek-headers",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Oracle",
                ),
                create_pkg_information(
                    name="kernel-firmware",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Oracle",
                ),
                create_pkg_information(
                    name="kernel-uek-firmware",
                    version="0.1",
                    release="1",
                    arch="x86_64",
                    packager="Oracle",
                ),
            ]


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


class GetInstalledPkgsWFingerprintsMocked(unit_tests.MockFunction):
    obj1 = create_pkg_information(name="pkg1", fingerprint="199e2f91fd431d51")  # RHEL
    obj2 = create_pkg_information(name="pkg2", fingerprint="72f97b74ec551f03")  # OL
    obj3 = create_pkg_information(
        name="gpg-pubkey", version="1.0.0", release="1", arch="x86_64", fingerprint="199e2f91fd431d51"  # RHEL
    )

    def __call__(self, *args, **kwargs):
        return [self.obj1, self.obj2, self.obj3]


class PrintPkgInfoMocked(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0
        self.pkgs = []

    def __call__(self, pkgs):
        self.called += 1
        self.pkgs = pkgs


class RemovePkgsMocked(unit_tests.MockFunction):
    def __init__(self):
        self.pkgs = None
        self.should_bkp = False
        self.critical = False

    def __call__(self, pkgs_to_remove, backup=False, critical=False):
        self.pkgs = pkgs_to_remove
        self.should_bkp = backup
        self.critical = critical


class DumbCallableObject(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0

    def __call__(self, *args, **kwargs):
        self.called += 1
        return


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

    def filter(self, name__glob, **kwargs):
        self.filter_called += 1
        if name__glob and name__glob == "installed_pkg":
            self._setup_pkg()
        elif name__glob:
            self.pkg_obj = None
        return self


class ReturnPackagesMocked(unit_tests.MockFunction):
    def __call__(self, patterns=None):
        if patterns:
            if "non_existing" in patterns:
                return []

        pkg_obj = TestPkgObj()
        pkg_obj.name = "installed_pkg"
        return [pkg_obj]


class TestPkgHandler(unit_tests.ExtendedTestCase):
    class GetInstalledPkgsWithFingerprintMocked(unit_tests.MockFunction):
        def __init__(self, data=None):
            self.data = data
            self.called = 0

        def __call__(self, *args, **kwargs):
            self.called += 1
            return self.data

    class GetInstalledPkgsByFingerprintMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return ["pkg1", "pkg2"]

    class IsFileMocked(unit_tests.MockFunction):
        def __init__(self, is_file):
            self.is_file = is_file

        def __call__(self, *args, **kwargs):
            return self.is_file

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

    @unit_tests.mock(pkghandler, "loggerinst", GetLoggerMocked())
    @unit_tests.mock(os.path, "isfile", IsFileMocked(is_file=False))
    @unit_tests.mock(os.path, "getsize", GetSizeMocked(file_size=0))
    def test_clear_versionlock_plugin_not_enabled(self):
        pkghandler.clear_versionlock()
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

    class CallYumCmdWDowngradesMocked(unit_tests.MockFunction):
        def __init__(self):
            self.cmd = ""
            self.pkgs = []

        def __call__(self, cmd, pkgs):
            self.cmd += "%s\n" % cmd
            self.pkgs += [pkgs]

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

        self.assertIn("No third party packages installed", pkghandler.loggerinst.info_msgs[0])

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
        self.assertIn("Only packages signed by", pkghandler.loggerinst.warning_msgs[0])

    @unit_tests.mock(tool_opts, "disablerepo", ["*", "rhel-7-extras-rpm"])
    @unit_tests.mock(tool_opts, "enablerepo", ["rhel-7-extras-rpm"])
    @unit_tests.mock(pkghandler, "loggerinst", GetLoggerMocked())
    def test_is_disable_and_enable_repos_has_same_repo(self):
        pkghandler.has_duplicate_repos_across_disablerepo_enablerepo_options()
        self.assertIn("Duplicate repositories were found", pkghandler.loggerinst.warning_msgs[0])

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
        self.assertIn(
            "Detected leftover boot kernel, changing to RHEL kernel", pkghandler.logging.getLogger.warning_msgs[0]
        )
        self.assertIn("/etc/sysconfig/kernel", utils.store_content_to_file.filename)
        self.assertIn("DEFAULTKERNEL=kernel", utils.store_content_to_file.content)
        self.assertNotIn("DEFAULTKERNEL=kernel-uek", utils.store_content_to_file.content)
        self.assertNotIn("DEFAULTKERNEL=kernel-core", utils.store_content_to_file.content)

        system_info.name = "Oracle Linux Server release 8.1"
        system_info.version = namedtuple("Version", ["major", "minor"])(8, 1)
        pkghandler.fix_default_kernel()
        self.assertTrue(len(pkghandler.logging.getLogger.info_msgs), 1)
        self.assertTrue(len(pkghandler.logging.getLogger.warning_msgs), 1)
        self.assertIn(
            "Detected leftover boot kernel, changing to RHEL kernel", pkghandler.logging.getLogger.warning_msgs[0]
        )
        self.assertIn("DEFAULTKERNEL=kernel", utils.store_content_to_file.content)
        self.assertNotIn("DEFAULTKERNEL=kernel-uek", utils.store_content_to_file.content)

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
        self.assertIn("DEFAULTKERNEL=kernel", utils.store_content_to_file.content)
        self.assertNotIn("DEFAULTKERNEL=kernel-plus", utils.store_content_to_file.content)

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
        self.assertEqual(len(pkghandler.logging.getLogger.warning_msgs), 0)


@pytest.mark.parametrize(
    ("version1", "version2", "expected"),
    (
        pytest.param(
            "kernel-core-0:4.18.0-240.10.1.el8_3.i86", "kernel-core-0:4.18.0-240.10.1.el8_3.i86", 0, id="NEVRA"
        ),
        pytest.param("kernel-core-0:123-5.fc35", "kernel-core-0:123-4.fc35", 1, id="NEVR"),
        pytest.param("kernel-core-123-3.fc35.aarch64", "kernel-core-123-4.fc35.aarch64", -1, id="NVRA"),
        pytest.param("kernel-3.10.0-1160.83.1.0.1.el7", "kernel-3.10.0-1160.83.1.el7", 1, id="NVR"),
        pytest.param(
            "kernel-core-0:4.6~pre16262021g84ef6bd9-3.fc35",
            "kernel-core-0:4.6~pre16262021g84ef6bd9-3.fc35",
            0,
            id="NEVR",
        ),
        pytest.param("kernel-core-2:8.2.3568-1.fc35", "kernel-core-2:8.2.3568-1.fc35", 0, id="NEVR"),
        pytest.param(
            "1:NetworkManager-1.18.8-2.0.1.el7_9.aarch64", "1:NetworkManager-1.18.8-1.0.1.el7_9.aarch64", 1, id="ENVRA"
        ),
        pytest.param("1:NetworkManager-1.18.8-2.0.1.el7_9", "1:NetworkManager-1.18.8-3.0.1.el7_9", -1, id="ENVR"),
        pytest.param("NetworkManager-1.18.8-2.0.1.el7_9", "1:NetworkManager-2.18.8-3.0.1.el7_9", -1, id="NVR&ENVR"),
        pytest.param("2:NetworkManager-1.18.8-2.0.1.el7_9", "0:NetworkManager-1.18.8-3.0.1.el7_9", 1, id="ENVR"),
    ),
)
def test_compare_package_versions(version1, version2, expected):
    assert pkghandler.compare_package_versions(version1, version2) == expected


@pytest.mark.parametrize(
    ("version1", "version2", "exception_message"),
    (
        (
            "kernel-core-0:390-287.fc36",
            "kernel-0:390-287.fc36",
            re.escape(
                "The package names ('kernel-core' and 'kernel') do not match. Can only compare versions for the same packages."
            ),
        ),
        (
            "kernel-core-0:390-287.fc36.aarch64",
            "kernel-core-0:391-287.fc36.i86",
            re.escape("The arches ('aarch64' and 'i86') do not match. Can only compare versions for the same arches."),
        ),
    ),
)
def test_compare_package_versions_warnings(version1, version2, exception_message):
    with pytest.raises(ValueError, match=exception_message):
        pkghandler.compare_package_versions(version1, version2)


PACKAGE_FORMATS = (
    pytest.param(
        "kernel-core-0:4.18.0-240.10.1.el8_3.i86", ("kernel-core", "0", "4.18.0", "240.10.1.el8_3", "i86"), id="NEVRA"
    ),
    pytest.param(
        "kernel-core-0:4.18.0-240.10.1.el8_3", ("kernel-core", "0", "4.18.0", "240.10.1.el8_3", None), id="NEVR"
    ),
    pytest.param(
        "1:NetworkManager-1.18.8-2.0.1.el7_9.aarch64",
        ("NetworkManager", "1", "1.18.8", "2.0.1.el7_9", "aarch64"),
        id="ENVRA",
    ),
    pytest.param(
        "1:NetworkManager-1.18.8-2.0.1.el7_9", ("NetworkManager", "1", "1.18.8", "2.0.1.el7_9", None), id="ENVR"
    ),
    pytest.param(
        "NetworkManager-1.18.8-2.0.1.el7_9.aarch64",
        ("NetworkManager", None, "1.18.8", "2.0.1.el7_9", "aarch64"),
        id="NVRA",
    ),
    pytest.param(
        "NetworkManager-1.18.8-2.0.1.el7_9", ("NetworkManager", None, "1.18.8", "2.0.1.el7_9", None), id="NVR"
    ),
    pytest.param(
        "bind-export-libs-32:9.11.4-26.P2.el7_9.13.x86_64",
        ("bind-export-libs", "32", "9.11.4", "26.P2.el7_9.13", "x86_64"),
        id="high epoch number",
    ),
    pytest.param("libgcc-8.5.0-4.el8_5.i686", ("libgcc", None, "8.5.0", "4.el8_5", "i686"), id="i686 package version"),
)


@pytest.mark.skipif(pkgmanager.TYPE == "yum", reason="cannot test dnf backend if dnf is not present")
def test_parse_pkg_string_dnf_called(monkeypatch):
    package = "kernel-core-0:4.18.0-240.10.1.el8_3.i86"
    parse_pkg_with_dnf_mock = mock.Mock(return_value=("kernel-core", "0", "4.18.0", "240.10.1.el8_3", "i86"))
    monkeypatch.setattr(pkghandler, "_parse_pkg_with_dnf", value=parse_pkg_with_dnf_mock)
    pkghandler.parse_pkg_string(package)
    parse_pkg_with_dnf_mock.assert_called_once()


@pytest.mark.skipif(pkgmanager.TYPE == "dnf", reason="cannot test yum backend if yum is not present")
def test_parse_pkg_string_yum_called(monkeypatch):
    package = "kernel-core-0:4.18.0-240.10.1.el8_3.i86"
    parse_pkg_with_yum_mock = mock.Mock(return_value=("kernel-core", "0", "4.18.0", "240.10.1.el8_3", "i86"))
    monkeypatch.setattr(pkghandler, "_parse_pkg_with_yum", value=parse_pkg_with_yum_mock)
    pkghandler.parse_pkg_string(package)
    parse_pkg_with_yum_mock.assert_called_once()


@pytest.mark.skipif(pkgmanager.TYPE == "dnf", reason="cannot test yum backend if yum is not present")
@pytest.mark.parametrize(
    ("package", "expected"),
    (PACKAGE_FORMATS),
)
def test_parse_pkg_with_yum(package, expected):
    assert pkghandler._parse_pkg_with_yum(package) == expected


@pytest.mark.skipif(pkgmanager.TYPE == "yum", reason="cannot test dnf backend if dnf is not present")
@pytest.mark.parametrize(
    ("package", "expected"),
    (PACKAGE_FORMATS),
)
def test_parse_pkg_with_dnf(package, expected):
    assert pkghandler._parse_pkg_with_dnf(package) == expected


@pytest.mark.skipif(pkgmanager.TYPE == "yum", reason="cannot test dnf backend if dnf is not present")
@pytest.mark.parametrize(
    ("package"),
    (
        ("not a valid package"),
        ("centos:0.1.0-34.aarch64"),
        ("name:0-10._12.aarch64"),
        ("kernel:0-10-1-2.aarch64"),
        ("foo-15.x86_64"),
    ),
)
def test_parse_pkg_with_dnf_value_error(package):
    with pytest.raises(ValueError):
        pkghandler._parse_pkg_with_dnf(package)


@pytest.mark.skipif(pkgmanager.TYPE == "dnf", reason="dnf parsing function will raise a different valueError")
@pytest.mark.parametrize(
    ("package", "name", "epoch", "version", "release", "arch", "expected"),
    (
        (
            "Network Manager:0-1.18.8-2.0.1.el7_9.aarch64",
            "Network Manager",
            "1",
            "1.18.8",
            "2.0.1.el7_9",
            "aarch64",
            re.escape("The following field(s) are invalid - name : Network Manager"),
        ),
        (
            "NetworkManager:01-1.18.8-2.0.1.el7_9.aarch64",
            "NetworkManager",
            "O1",
            "1.18.8",
            "2.0.1.el7_9",
            "aarch64",
            re.escape("The following field(s) are invalid - epoch : O1"),
        ),
        (
            "NetworkManager:1-1.1 8.8-2.0.1.el7_9.aarch64",
            "NetworkManager",
            "1",
            "1.1 8.8",
            "2.0.1.el7_9",
            "aarch64",
            re.escape("The following field(s) are invalid - version : 1.1 8.8"),
        ),
        (
            "NetworkManager:1-1.18.8-2.0.1-el7_9.aarch64",
            "NetworkManager",
            "1",
            "1.18.8",
            "2.0.1-el7_9",
            "aarch64",
            re.escape("The following field(s) are invalid - release : 2.0.1-el7_9"),
        ),
        (
            "NetworkManager:1-1.18.8-2.0.1.el7_9.aarch65",
            "NetworkManager",
            "1",
            "1.18.8",
            "2.0.1.el7_9",
            "aarch65",
            re.escape("The following field(s) are invalid - arch : aarch65"),
        ),
        (
            "Network Manager:01-1.1 8.8-2.0.1-el7_9.aarch65",
            "Network Manager",
            "O1",
            "1.1 8.8",
            "2.0.1-el7_9",
            "aarch65",
            re.escape(
                "The following field(s) are invalid - name : Network Manager, epoch : O1, version : 1.1 8.8, release : 2.0.1-el7_9, arch : aarch65"
            ),
        ),
        (
            "1-18.8-2.0.1.el7_9.aarch64",
            None,
            "1",
            "1.18.8",
            "2.0.1.el7_9",
            "aarch64",
            re.escape("The following field(s) are invalid - name : [None]"),
        ),
        (
            "NetworkManager:1-2.0.1.el7_9.aarch64",
            "NetworkManager",
            "1",
            None,
            "2.0.1.el7_9",
            "aarch64",
            re.escape("The following field(s) are invalid - version : [None]"),
        ),
        (
            "NetworkManager:1-1.18.8.el7_9.aarch64",
            "NetworkManager",
            "1",
            "1.18.8",
            None,
            "aarch64",
            re.escape("The following field(s) are invalid - release : [None]"),
        ),
    ),
)
def test_validate_parsed_fields_invalid(package, name, epoch, version, release, arch, expected):
    with pytest.raises(ValueError, match=expected):
        pkghandler._validate_parsed_fields(package, name, epoch, version, release, arch)


@pytest.mark.skipif(pkgmanager.TYPE == "dnf", reason="dnf parsing function will raise a different valueError")
@pytest.mark.parametrize(
    ("package", "expected"),
    (
        (
            "0:Network Manager-1.1.1-82.aarch64",
            re.escape("The following field(s) are invalid - name : Network Manager"),
        ),
        (
            "foo-15.x86_64",
            re.escape(
                "Invalid package - foo-15.x86_64, packages need to be in one of the following formats: NEVRA, NEVR, NVRA, NVR, ENVRA, ENVR. Reason: The total length of the parsed package fields does not equal the package length,"
            ),
        ),
        (
            "notavalidpackage",
            re.escape(
                "Invalid package - notavalidpackage, packages need to be in one of the following formats: NEVRA, NEVR, NVRA, NVR, ENVRA, ENVR. Reason: The total length of the parsed package fields does not equal the package length,"
            ),
        ),
    ),
)
def test_validate_parsed_fields_invalid_package(package, expected):
    with pytest.raises(ValueError, match=expected):
        pkghandler.parse_pkg_string(package)


@pytest.mark.parametrize(
    ("package"),
    (
        pytest.param("kernel-core-0:4.18.0-240.10.1.el8_3.i86", id="NEVRA"),
        pytest.param("kernel-core-0:4.18.0-240.10.1.el8_3", id="NEVR"),
        pytest.param(
            "1:NetworkManager-1.18.8-2.0.1.el7_9.aarch64",
            id="ENVRA",
        ),
        pytest.param("1:NetworkManager-1.18.8-2.0.1.el7_9", id="ENVR"),
        pytest.param(
            "NetworkManager-1.18.8-2.0.1.el7_9.aarch64",
            id="NVRA",
        ),
        pytest.param("NetworkManager-1.18.8-2.0.1.el7_9", id="NVR"),
    ),
)
def test_validate_parsed_fields_valid(package):
    pkghandler.parse_pkg_string(package)


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
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
def test_get_packages_to_update_yum_no_more_mirrors(monkeypatch, caplog):
    monkeypatch.setattr(
        pkgmanager.YumBase,
        "doPackageLists",
        mock.Mock(side_effect=pkgmanager.Errors.NoMoreMirrorsRepoError("Failed to connect to repository.")),
    )
    with pytest.raises(pkgmanager.Errors.NoMoreMirrorsRepoError, match="Failed to connect to repository."):
        _get_packages_to_update_yum()


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


class TestInstallGpgKeys(object):
    data_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "../data/version-independent"))
    gpg_keys_dir = os.path.join(data_dir, "gpg-keys")

    def test_install_gpg_keys(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(utils, "DATA_DIR", self.data_dir)

        # Prevent RestorableRpmKey from actually performing any work
        enable_mock = mock.Mock()
        monkeypatch.setattr(backup.RestorableRpmKey, "enable", enable_mock)

        pkghandler.install_gpg_keys()

        # Get the filenames for every gpg key registered with backup_control
        restorable_keys = set()
        for key in global_backup_control._restorables:
            restorable_keys.add(key.keyfile)

        gpg_file_glob = os.path.join(self.gpg_keys_dir, "*")
        gpg_keys = glob.glob(gpg_file_glob)

        # Make sure we have some keys in the data dir to check
        assert len(gpg_keys) != 0

        # check that all of the keys from data_dir have been registered with the backup_control.
        # We'll test what the restorable keys do in backup_test (for the RestorableKey class)
        assert len(restorable_keys) == len(global_backup_control._restorables)
        for gpg_key in gpg_keys:
            assert gpg_key in restorable_keys

    def test_install_gpg_keys_fail_create_restorable(self, monkeypatch, tmpdir, global_backup_control):
        keys_dir = os.path.join(str(tmpdir), "gpg-keys")
        os.mkdir(keys_dir)
        bad_gpg_key_filename = os.path.join(keys_dir, "bad-key")
        with open(bad_gpg_key_filename, "w") as f:
            f.write("BAD_DATA")

        monkeypatch.setattr(utils, "DATA_DIR", str(tmpdir))

        with pytest.raises(SystemExit, match="Importing the GPG key into rpm failed:\n .*"):
            pkghandler.install_gpg_keys()


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
    ("pkgs", "expected"),
    (
        (
            [
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-1",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="not-the-centos7-fingerprint",
                    signature="test",
                )
            ],
            [],
        ),
        (
            [
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-1",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="24c6a8a7f4a80eb5",
                    signature="test",
                )
            ],
            ["pkg-1.x86_64"],
        ),
        (
            [
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-1",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="24c6a8a7f4a80eb5",
                    signature="test",
                ),
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-2",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="24c6a8a7f4a80eb5",
                    signature="test",
                ),
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-3",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="24c6a8a7f4a80eb5",
                    signature="test",
                ),
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-4",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="24c6a8a7f4a80eb5",
                    signature="test",
                ),
            ],
            ["pkg-1.x86_64", "pkg-2.x86_64", "pkg-3.x86_64", "pkg-4.x86_64"],
        ),
        (
            [
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-1",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="24c6a8a7f4a80eb5",
                    signature="test",
                ),
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="pkg-2",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="this-is-a-fingerprint",
                    signature="test",
                ),
            ],
            ["pkg-1.x86_64"],
        ),
        (
            [
                create_pkg_information(
                    packager="test",
                    vendor="test",
                    name="gpg-pubkey",
                    epoch="0",
                    release="1.0.0",
                    version="1",
                    arch="x86_64",
                    fingerprint="test",
                    signature="test",
                )
            ],
            [],
        ),
    ),
)
@centos7
def test_get_system_packages_for_replacement(pretend_os, pkgs, expected, monkeypatch):
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", value=lambda: pkgs)

    result = pkghandler.get_system_packages_for_replacement()
    assert expected == result


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
@pytest.mark.parametrize(
    ("name", "version", "release", "arch", "total_pkgs_installed"),
    (
        (None, None, None, None, 1),
        ("installed_pkg", "1", "20.1", "x86_64", 1),
        ("non_existing", None, None, None, 0),  # Special name to return an empty list.
    ),
)
def test_get_installed_pkg_objects_yum(name, version, release, arch, total_pkgs_installed, monkeypatch):
    monkeypatch.setattr(pkgmanager.rpmsack.RPMDBPackageSack, "returnPackages", ReturnPackagesMocked())
    pkgs = pkghandler.get_installed_pkg_objects(name, version, release, arch)

    assert len(pkgs) == total_pkgs_installed
    if total_pkgs_installed > 0:
        assert pkgs[0].name == "installed_pkg"


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
@pytest.mark.parametrize(
    ("name", "version", "release", "arch", "total_pkgs_installed"),
    (
        (None, None, None, None, 1),
        ("installed_pkg", "1", "20.1", "x86_64", 1),
        ("non_existing", None, None, None, 0),
    ),
)
def test_get_installed_pkg_objects_dnf(name, version, release, arch, total_pkgs_installed, monkeypatch):
    monkeypatch.setattr(pkgmanager.query, "Query", QueryMocked())
    pkgs = pkghandler.get_installed_pkg_objects(name, version, release, arch)

    assert len(pkgs) == total_pkgs_installed
    if total_pkgs_installed > 0:
        assert pkgs[0].name == "installed_pkg"


@centos7
def test_get_installed_pkgs_by_fingerprint_correct_fingerprint(pretend_os, monkeypatch):
    package = [
        create_pkg_information(
            packager="test",
            vendor="test",
            name="pkg1",
            epoch="0",
            version="1.0.0",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),  # RHEL
        create_pkg_information(
            packager="test",
            vendor="test",
            name="pkg2",
            epoch="0",
            version="1.0.0",
            release="1",
            arch="x86_64",
            fingerprint="72f97b74ec551f03",
            signature="test",
        ),  # OL
        create_pkg_information(
            packager="test",
            vendor="test",
            name="gpg-pubkey",
            epoch="0",
            version="1.0.0",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),
    ]
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda name: package)
    pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint("199e2f91fd431d51")

    for pkg in pkgs_by_fingerprint:
        assert pkg in ("pkg1.x86_64", "gpg-pubkey.x86_64")


@centos7
def test_get_installed_pkgs_by_fingerprint_incorrect_fingerprint(pretend_os, monkeypatch):
    package = [
        create_pkg_information(
            packager="test",
            vendor="test",
            name="pkg1",
            epoch="0",
            version="1.0.0",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),  # RHEL
        create_pkg_information(
            packager="test",
            vendor="test",
            name="pkg2",
            epoch="0",
            version="1.0.0",
            release="1",
            arch="x86_64",
            fingerprint="72f97b74ec551f03",
            signature="test",
        ),  # OL
        create_pkg_information(
            packager="test",
            vendor="test",
            name="gpg-pubkey",
            epoch="0",
            version="1.0.0",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),
    ]
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda name: package)
    pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint("non-existing fingerprint")

    assert not pkgs_by_fingerprint


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
@centos7
def test_print_pkg_info_yum(pretend_os, monkeypatch):
    packages = [
        create_pkg_information(
            packager="Oracle",
            vendor="(none)",
            name="pkg1",
            epoch="0",
            version="0.1",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),  # RHEL
        create_pkg_information(
            name="pkg2",
            epoch="0",
            version="0.1",
            release="1",
            arch="x86_64",
            fingerprint="72f97b74ec551f03",
            signature="test",
        ),  # OL
        create_pkg_information(
            name="gpg-pubkey",
            epoch="0",
            version="0.1",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),
    ]

    monkeypatch.setattr(
        utils,
        "run_subprocess",
        mock.Mock(
            return_value=(
                """\
C2R 0:pkg1-0.1-1.x86_64&anaconda
C2R 0:pkg2-0.1-1.x86_64&
C2R 0:gpg-pubkey-0.1-1.x86_64&test
    """,
                0,
            )
        ),
    )

    result = pkghandler.print_pkg_info(packages)
    assert re.search(
        r"^Package\s+Vendor/Packager\s+Repository$",
        result,
        re.MULTILINE,
    )
    assert re.search(
        r"^0:pkg1-0\.1-1\.x86_64\s+Oracle\s+anaconda$",
        result,
        re.MULTILINE,
    )
    assert re.search(r"^0:pkg2-0\.1-1\.x86_64\s+N/A\s+N/A$", result, re.MULTILINE)
    assert re.search(
        r"^0:gpg-pubkey-0\.1-1\.x86_64\s+N/A\s+test$",
        result,
        re.MULTILINE,
    )


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
@centos8
def test_print_pkg_info_dnf(pretend_os, monkeypatch):
    packages = [
        create_pkg_information(
            packager="Oracle",
            vendor="(none)",
            name="pkg1",
            epoch="0",
            version="0.1",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",  # RHEL
            signature="test",
        ),
        create_pkg_information(
            name="pkg2",
            epoch="0",
            version="0.1",
            release="1",
            arch="x86_64",
            fingerprint="72f97b74ec551f03",
            signature="test",
        ),  # OL
        create_pkg_information(
            name="gpg-pubkey",
            epoch="0",
            version="0.1",
            release="1",
            arch="x86_64",
            fingerprint="199e2f91fd431d51",
            signature="test",
        ),
    ]

    monkeypatch.setattr(
        utils,
        "run_subprocess",
        mock.Mock(
            return_value=(
                """\
C2R pkg1-0:0.1-1.x86_64&anaconda
C2R pkg2-0:0.1-1.x86_64&@@System
C2R gpg-pubkey-0:0.1-1.x86_64&test
    """,
                0,
            )
        ),
    )

    result = pkghandler.print_pkg_info(packages)

    assert re.search(
        r"^pkg1-0:0\.1-1\.x86_64\s+Oracle\s+anaconda$",
        result,
        re.MULTILINE,
    )
    assert re.search(r"^pkg2-0:0\.1-1\.x86_64\s+N/A\s+@@System$", result, re.MULTILINE)
    assert re.search(
        r"^gpg-pubkey-0:0\.1-1\.x86_64\s+N/A\s+test$",
        result,
        re.MULTILINE,
    )


class GetInstalledPkgObjectsWDiffFingerprintMocked(unit_tests.MockFunction):
    def __call__(self, fingerprints, name=""):
        if name and name != "installed_pkg":
            return []
        if "rhel_fingerprint" in fingerprints:
            pkg_obj = create_pkg_information(
                packager="Oracle", vendor=None, name="installed_pkg", version="0.1", release="1", arch="x86_64"
            )
        else:
            pkg_obj = create_pkg_information(
                packager="Red Hat",
                name="installed_pkg",
                version="0.1",
                release="1",
                arch="x86_64",
            )
        return [pkg_obj]


def test_get_packages_to_remove(monkeypatch):
    monkeypatch.setattr(system_info, "fingerprints_rhel", ["rhel_fingerprint"])
    monkeypatch.setattr(
        pkghandler, "get_installed_pkgs_w_different_fingerprint", GetInstalledPkgObjectsWDiffFingerprintMocked()
    )
    original_func = pkghandler._get_packages_to_remove.__wrapped__
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", mock_decorator(original_func))

    result = pkghandler._get_packages_to_remove(["installed_pkg", "not_installed_pkg"])
    assert len(result) == 1
    assert result[0].nevra.name == "installed_pkg"


def test_remove_pkgs_with_confirm(monkeypatch):
    monkeypatch.setattr(utils, "ask_to_continue", DumbCallableObject())
    monkeypatch.setattr(pkghandler, "print_pkg_info", DumbCallable())
    monkeypatch.setattr(pkghandler, "remove_pkgs", RemovePkgsMocked())

    pkghandler.remove_pkgs_with_confirm(
        [
            create_pkg_information(
                packager="Oracle", vendor=None, name="installed_pkg", version="0.1", release="1", arch="x86_64"
            )
        ]
    )

    assert len(pkghandler.remove_pkgs.pkgs) == 1
    assert pkghandler.remove_pkgs.pkgs[0] == "installed_pkg-0.1-1.x86_64"


@pytest.mark.parametrize(
    ("signature", "expected"),
    (
        ("RSA/SHA256, Sun Feb  7 18:35:40 2016, Key ID 73bde98381b46521", "73bde98381b46521"),
        ("RSA/SHA256, Sun Feb  7 18:35:40 2016, teest ID 73bde98381b46521", "none"),
        ("test", "none"),
    ),
)
def test_get_pkg_fingerprint(signature, expected):
    fingerprint = pkghandler._get_pkg_fingerprint(signature)
    assert fingerprint == expected


@pytest.mark.parametrize(
    ("package", "expected"),
    (
        (
            create_pkg_information(
                vendor="Oracle",
            ),
            "Oracle",
        ),
        (
            create_pkg_information(
                packager="Oracle",
            ),
            "N/A",
        ),
    ),
)
def test_get_vendor(package, expected):
    assert pkghandler.get_vendor(package) == expected


@pytest.mark.parametrize(
    ("pkgmanager_name", "package", "include_zero_epoch", "expected"),
    (
        (
            "dnf",
            create_pkg_information(name="pkg", epoch="1", version="2", release="3", arch="x86_64"),
            True,
            "pkg-1:2-3.x86_64",
        ),
        (
            "yum",
            create_pkg_information(name="pkg", epoch="1", version="2", release="3", arch="x86_64"),
            True,
            "1:pkg-2-3.x86_64",
        ),
        (
            "dnf",
            create_pkg_information(name="pkg", epoch="0", version="2", release="3", arch="x86_64"),
            False,
            "pkg-2-3.x86_64",
        ),
        (
            "yum",
            create_pkg_information(name="pkg", epoch="0", version="2", release="3", arch="x86_64"),
            False,
            "pkg-2-3.x86_64",
        ),
        (
            "yum",
            create_pkg_information(name="pkg", epoch="0", version="2", release="3", arch="x86_64"),
            True,
            "0:pkg-2-3.x86_64",
        ),
    ),
)
def test_get_pkg_nevra(pkgmanager_name, package, include_zero_epoch, expected, monkeypatch):
    monkeypatch.setattr(pkgmanager, "TYPE", pkgmanager_name)
    assert pkghandler.get_pkg_nevra(package, include_zero_epoch) == expected


@pytest.mark.parametrize(
    ("fingerprint_orig_os", "expected_count", "expected_pkgs"),
    (
        (["24c6a8a7f4a80eb5", "a963bbdbf533f4fa"], 0, 1),
        (["72f97b74ec551f03"], 0, 0),
    ),
)
def test_get_third_party_pkgs(fingerprint_orig_os, expected_count, expected_pkgs, monkeypatch):
    monkeypatch.setattr(utils, "ask_to_continue", DumbCallableObject())
    monkeypatch.setattr(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    monkeypatch.setattr(system_info, "fingerprints_orig_os", fingerprint_orig_os)
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", GetInstalledPkgsWFingerprintsMocked())

    pkgs = pkghandler.get_third_party_pkgs()

    assert pkghandler.print_pkg_info.called == expected_count
    assert len(pkgs) == expected_pkgs


def test_list_non_red_hat_pkgs_left(monkeypatch):
    monkeypatch.setattr(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", GetInstalledPkgsWFingerprintsMocked())
    pkghandler.list_non_red_hat_pkgs_left()

    assert len(pkghandler.print_pkg_info.pkgs) == 1
    assert pkghandler.print_pkg_info.pkgs[0].nevra.name == "pkg2"


@centos7
def test_install_rhel_kernel(pretend_os, monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    monkeypatch.setattr(pkghandler, "handle_no_newer_rhel_kernel_available", DumbCallableObject())
    monkeypatch.setattr(
        pkghandler, "get_installed_pkgs_w_different_fingerprint", GetInstalledPkgsWDifferentFingerprintMocked()
    )

    # 1st scenario: kernels collide; the installed one is already a RHEL kernel = no action.
    kernel_package = "kernel-3.10.0-1127.19.1.el7.x86_64"

    utils.run_subprocess.output = "Package %s already installed and latest version" % kernel_package
    pkghandler.get_installed_pkgs_w_different_fingerprint.is_only_rhel_kernel_installed = True

    update_kernel = pkghandler.install_rhel_kernel()

    assert not update_kernel

    # 2nd scenario: kernels collide; the installed one is from third party
    # = older-version RHEL kernel is to be installed.
    pkghandler.get_installed_pkgs_w_different_fingerprint.is_only_rhel_kernel_installed = False

    update_kernel = pkghandler.install_rhel_kernel()

    assert update_kernel

    # 3rd scenario: kernels do not collide; the RHEL one gets installed.
    utils.run_subprocess.output = "Installed:\nkernel"

    update_kernel = pkghandler.install_rhel_kernel()

    assert not update_kernel


@centos7
def test_install_rhel_kernel_already_installed_regexp(pretend_os, monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    monkeypatch.setattr(
        pkghandler, "get_installed_pkgs_w_different_fingerprint", GetInstalledPkgsWDifferentFingerprintMocked()
    )

    # RHEL 7
    utils.run_subprocess.output = "Package kernel-2.6.32-754.33.1.el6.x86_64 already installed and latest version"

    pkghandler.install_rhel_kernel()

    assert pkghandler.get_installed_pkgs_w_different_fingerprint.called == 1

    # RHEL 8
    utils.run_subprocess.output = "Package kernel-4.18.0-193.el8.x86_64 is already installed."

    pkghandler.install_rhel_kernel()
    assert pkghandler.get_installed_pkgs_w_different_fingerprint.called == 2


def test_remove_non_rhel_kernels(monkeypatch):
    monkeypatch.setattr(
        pkghandler, "get_installed_pkgs_w_different_fingerprint", GetInstalledPkgsWDifferentFingerprintMocked()
    )
    monkeypatch.setattr(pkghandler, "print_pkg_info", DumbCallableObject())
    monkeypatch.setattr(pkghandler, "remove_pkgs", RemovePkgsMocked())

    removed_pkgs = pkghandler.remove_non_rhel_kernels()

    assert len(removed_pkgs) == 6
    assert [p.nevra.name for p in removed_pkgs] == [
        "kernel",
        "kernel-uek",
        "kernel-headers",
        "kernel-uek-headers",
        "kernel-firmware",
        "kernel-uek-firmware",
    ]


def test_install_additional_rhel_kernel_pkgs(monkeypatch):
    monkeypatch.setattr(
        pkghandler, "get_installed_pkgs_w_different_fingerprint", GetInstalledPkgsWDifferentFingerprintMocked()
    )
    monkeypatch.setattr(pkghandler, "print_pkg_info", DumbCallableObject())
    monkeypatch.setattr(pkghandler, "remove_pkgs", RemovePkgsMocked())
    monkeypatch.setattr(pkghandler, "call_yum_cmd", CallYumCmdMocked())

    removed_pkgs = pkghandler.remove_non_rhel_kernels()
    pkghandler.install_additional_rhel_kernel_pkgs(removed_pkgs)
    assert pkghandler.call_yum_cmd.called == 2


@pytest.mark.parametrize(
    ("package_name", "subprocess_output", "expected", "expected_command"),
    (
        (
            "libgcc*",
            "C2R CentOS Buildsys <bugs@centos.org>&CentOS&libgcc-0:8.5.0-4.el8_5.i686&RSA/SHA256, Fri Nov 12 21:15:26 2021, Key ID 05b555b38483c65d",
            [
                PackageInformation(
                    packager="CentOS Buildsys <bugs@centos.org>",
                    vendor="CentOS",
                    nevra=PackageNevra(
                        name="libgcc",
                        epoch="0",
                        version="8.5.0",
                        release="4.el8_5",
                        arch="i686",
                    ),
                    fingerprint="05b555b38483c65d",
                    signature="RSA/SHA256, Fri Nov 12 21:15:26 2021, Key ID 05b555b38483c65d",
                )
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-qa",
                "libgcc*",
            ],
        ),
        (
            "libgcc-0:8.5.0-4.el8_5.i686",
            "C2R CentOS Buildsys <bugs@centos.org>&CentOS&libgcc-0:8.5.0-4.el8_5.i686&RSA/SHA256, Fri Nov 12 21:15:26 2021, Key ID 05b555b38483c65d",
            [
                PackageInformation(
                    packager="CentOS Buildsys <bugs@centos.org>",
                    vendor="CentOS",
                    nevra=PackageNevra(
                        name="libgcc",
                        epoch="0",
                        version="8.5.0",
                        release="4.el8_5",
                        arch="i686",
                    ),
                    fingerprint="05b555b38483c65d",
                    signature="RSA/SHA256, Fri Nov 12 21:15:26 2021, Key ID 05b555b38483c65d",
                )
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-q",
                "libgcc-0:8.5.0-4.el8_5.i686",
            ],
        ),
        (
            "rpmlint-fedora-license-data-0:1.17-1.fc37.noarch",
            "C2R Fedora Project&Fedora Project&rpmlint-fedora-license-data-0:1.17-1.fc37.noarch&RSA/SHA256, Wed 05 Apr 2023 14:27:35 -03, Key ID f55ad3fb5323552a",
            [
                PackageInformation(
                    packager="Fedora Project",
                    vendor="Fedora Project",
                    nevra=PackageNevra(
                        name="rpmlint-fedora-license-data", epoch="0", version="1.17", release="1.fc37", arch="noarch"
                    ),
                    fingerprint="f55ad3fb5323552a",
                    signature="RSA/SHA256, Wed 05 Apr 2023 14:27:35 -03, Key ID f55ad3fb5323552a",
                )
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-q",
                "rpmlint-fedora-license-data-0:1.17-1.fc37.noarch",
            ],
        ),
        (
            "rpmlint-fedora-license-data-0:1.17-1.fc37.noarch",
            """
            C2R Fedora Project&Fedora Project&rpmlint-fedora-license-data-0:1.17-1.fc37.noarch&RSA/SHA256, Wed 05 Apr 2023 14:27:35 -03, Key ID f55ad3fb5323552a
            test test what a line
            """,
            [
                PackageInformation(
                    packager="Fedora Project",
                    vendor="Fedora Project",
                    nevra=PackageNevra(
                        name="rpmlint-fedora-license-data", epoch="0", version="1.17", release="1.fc37", arch="noarch"
                    ),
                    fingerprint="f55ad3fb5323552a",
                    signature="RSA/SHA256, Wed 05 Apr 2023 14:27:35 -03, Key ID f55ad3fb5323552a",
                )
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-q",
                "rpmlint-fedora-license-data-0:1.17-1.fc37.noarch",
            ],
        ),
        (
            "whatever",
            "random line",
            [],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-q",
                "whatever",
            ],
        ),
        (
            "*",
            """
            C2R Fedora Project&Fedora Project&fonts-filesystem-1:2.0.5-9.fc37.noarch&RSA/SHA256, Tue 23 Aug 2022 08:06:00 -03, Key ID f55ad3fb5323552a
            C2R Fedora Project&Fedora Project&fedora-logos-0:36.0.0-3.fc37.noarch&RSA/SHA256, Thu 21 Jul 2022 02:54:29 -03, Key ID f55ad3fb5323552a
            """,
            [
                PackageInformation(
                    packager="Fedora Project",
                    vendor="Fedora Project",
                    nevra=PackageNevra(
                        name="fonts-filesystem", epoch="1", version="2.0.5", release="9.fc37", arch="noarch"
                    ),
                    fingerprint="f55ad3fb5323552a",
                    signature="RSA/SHA256, Tue 23 Aug 2022 08:06:00 -03, Key ID f55ad3fb5323552a",
                ),
                PackageInformation(
                    packager="Fedora Project",
                    vendor="Fedora Project",
                    nevra=PackageNevra(
                        name="fedora-logos", epoch="0", version="36.0.0", release="3.fc37", arch="noarch"
                    ),
                    fingerprint="f55ad3fb5323552a",
                    signature="RSA/SHA256, Thu 21 Jul 2022 02:54:29 -03, Key ID f55ad3fb5323552a",
                ),
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-qa",
                "*",
            ],
        ),
        (
            "*",
            """
            C2R Fedora Project&Fedora Project&fonts-filesystem-1:2.0.5-9.fc37.noarch&RSA/SHA256, Tue 23 Aug 2022 08:06:00 -03, Key ID f55ad3fb5323552a
            C2R Fedora Project&Fedora Project&fedora-logos-0:36.0.0-3.fc37.noarch&RSA/SHA256, Thu 21 Jul 2022 02:54:29 -03, Key ID f55ad3fb5323552a
            testest what a line
            """,
            [
                PackageInformation(
                    packager="Fedora Project",
                    vendor="Fedora Project",
                    nevra=PackageNevra(
                        name="fonts-filesystem", epoch="1", version="2.0.5", release="9.fc37", arch="noarch"
                    ),
                    fingerprint="f55ad3fb5323552a",
                    signature="RSA/SHA256, Tue 23 Aug 2022 08:06:00 -03, Key ID f55ad3fb5323552a",
                ),
                PackageInformation(
                    packager="Fedora Project",
                    vendor="Fedora Project",
                    nevra=PackageNevra(
                        name="fedora-logos", epoch="0", version="36.0.0", release="3.fc37", arch="noarch"
                    ),
                    fingerprint="f55ad3fb5323552a",
                    signature="RSA/SHA256, Thu 21 Jul 2022 02:54:29 -03, Key ID f55ad3fb5323552a",
                ),
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-qa",
                "*",
            ],
        ),
    ),
)
def test_get_installed_pkg_information(package_name, subprocess_output, expected, expected_command, monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    utils.run_subprocess.output = subprocess_output

    result = pkghandler.get_installed_pkg_information(package_name)
    assert utils.run_subprocess.cmd == expected_command
    assert result == expected


def test_get_installed_pkg_information_value_error(monkeypatch, caplog):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    utils.run_subprocess.output = "C2R Fedora Project&Fedora Project&fonts-filesystem-a:aabb.d.1-l.fc37.noarch&RSA/SHA256, Tue 23 Aug 2022 08:06:00 -03, Key ID f55ad3fb5323552a"

    result = pkghandler.get_installed_pkg_information()
    assert not result
    assert "Failed to parse a package" in caplog.records[-1].message


def test_remove_excluded_pkgs(monkeypatch):
    monkeypatch.setattr(system_info, "excluded_pkgs", ["installed_pkg", "not_installed_pkg"])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject())
    monkeypatch.setattr(pkghandler, "remove_pkgs_with_confirm", CommandCallableObject())
    pkghandler.remove_excluded_pkgs()

    assert pkghandler._get_packages_to_remove.called == 1
    assert pkghandler.remove_pkgs_with_confirm.called == 1
    assert pkghandler._get_packages_to_remove.command == system_info.excluded_pkgs


def test_remove_repofile_pkgs(monkeypatch):
    monkeypatch.setattr(system_info, "repofile_pkgs", ["installed_pkg", "not_installed_pkg"])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject())
    monkeypatch.setattr(pkghandler, "remove_pkgs_with_confirm", CommandCallableObject())
    pkghandler.remove_repofile_pkgs()

    assert pkghandler._get_packages_to_remove.called == 1
    assert pkghandler.remove_pkgs_with_confirm.called == 1
    assert pkghandler._get_packages_to_remove.command == system_info.repofile_pkgs


@pytest.mark.parametrize(
    ("packages", "subprocess_output", "expected_result"),
    (
        (
            ["0:eog-44.1-1.fc38.x86_64", "0:gnome-backgrounds-44.0-1.fc38.noarch", "0:gnome-maps-44.1-1.fc38.x86_64"],
            """\
                C2R 0:eog-44.1-1.fc38.x86_64&updates
                C2R 0:gnome-backgrounds-44.0-1.fc38.noarch&fedora
                C2R 0:gnome-maps-44.1-1.fc38.x86_64&updates
            """,
            {
                "0:eog-44.1-1.fc38.x86_64": "updates",
                "0:gnome-backgrounds-44.0-1.fc38.noarch": "fedora",
                "0:gnome-maps-44.1-1.fc38.x86_64": "updates",
            },
        ),
        (
            ["0:eog-44.1-1.fc38.x86_64", "0:gnome-backgrounds-44.0-1.fc38.noarch", "0:gnome-maps-44.1-1.fc38.x86_64"],
            """\
                C2R 0:eog-44.1-1.fc38.x86_64&updates
                C2R 0:gnome-backgrounds-44.0-1.fc38.noarch&fedora
                C2R 0:gnome-maps-44.1-1.fc38.x86_64&updates
                test line without identifier
            """,
            {
                "0:eog-44.1-1.fc38.x86_64": "updates",
                "0:gnome-backgrounds-44.0-1.fc38.noarch": "fedora",
                "0:gnome-maps-44.1-1.fc38.x86_64": "updates",
            },
        ),
        (
            ["0:eog-44.1-1.fc38.x86_64", "0:gnome-backgrounds-44.0-1.fc38.noarch", "0:gnome-maps-44.1-1.fc38.x86_64"],
            """\
                test line without identifier
            """,
            {},
        ),
    ),
)
@centos7
def test_get_package_repositories(pretend_os, packages, subprocess_output, expected_result, monkeypatch, caplog):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    utils.run_subprocess.output = subprocess_output

    result = pkghandler._get_package_repositories(packages)
    assert expected_result == result
    if caplog.records[-1].message:
        assert "Got a line without the C2R identifier" in caplog.records[-1].message


@centos7
def test_get_package_repositories_repoquery_failure(pretend_os, monkeypatch, caplog):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
    utils.run_subprocess.ret_code = 1
    utils.run_subprocess.output = "failed"

    packages = ["0:gnome-backgrounds-44.0-1.fc38.noarch", "0:eog-44.1-1.fc38.x86_64", "0:gnome-maps-44.1-1.fc38.x86_64"]
    result = pkghandler._get_package_repositories(packages)

    assert "Repoquery exited with return code 1 and with output: failed" in caplog.records[-1].message
    for package in result:
        assert package in packages
        assert result[package] == "N/A"
