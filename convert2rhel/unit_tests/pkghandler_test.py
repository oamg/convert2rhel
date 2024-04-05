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
__metaclass__ = type


import glob
import os
import re

from collections import namedtuple

import pytest
import rpm
import six

from convert2rhel import pkghandler, pkgmanager, unit_tests, utils
from convert2rhel.backup.certs import RestorableRpmKey
from convert2rhel.backup.files import RestorableFile
from convert2rhel.pkghandler import (
    PackageInformation,
    PackageNevra,
    _get_packages_to_update_dnf,
    _get_packages_to_update_yum,
    get_total_packages_to_update,
)
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import (
    CallYumCmdMocked,
    DownloadPkgMocked,
    FormatPkgInfoMocked,
    GetInstalledPkgInformationMocked,
    GetInstalledPkgsByFingerprintMocked,
    GetInstalledPkgsWDifferentFingerprintMocked,
    RemovePkgsMocked,
    RunSubprocessMocked,
    StoreContentToFileMocked,
    SysExitCallableObject,
    TestPkgObj,
    create_pkg_information,
    create_pkg_obj,
    is_rpm_based_os,
    mock_decorator,
)
from convert2rhel.unit_tests.conftest import all_systems, centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


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


class FakeDnfQuery:
    def __init__(self, *args, **kwargs):
        self.instantiation_args = args
        self.instantiation_kwargs = kwargs

        self.filter_called = 0
        self.installed_called = 0
        self.stop_iteration = False

        self._setup_pkg()

    def _setup_pkg(self):
        self.pkg_obj = TestPkgObj()
        self.pkg_obj.name = "installed_pkg"

    def __iter__(self):  # pylint: disable=non-iterator-returned
        return self

    def __next__(self):
        if self.stop_iteration or not self.pkg_obj:
            self.stop_iteration = False
            raise StopIteration
        self.stop_iteration = True
        return self.pkg_obj

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


class ReturnPackagesObject(unit_tests.MockFunctionObject):
    """
    Code using this needs to pass in spec when they instantiate it.
    """

    def __call__(self, *args, **kwargs):
        super(ReturnPackagesObject, self).__call__(*args, **kwargs)

        patterns = kwargs.get("patterns", None)
        if patterns:
            if "non_existing" in patterns:
                return []

        pkg_obj = TestPkgObj()
        pkg_obj.name = "installed_pkg"
        return [pkg_obj]


class FakeTransactionSet:
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
        if key != "name":  # everything other than 'name' is unsupported ATM :)
            return []
        if not value:
            return db
        else:
            return [db_entry for db_entry in db if db_entry[rpm.RPMTAG_NAME] == value]


class TestClearVersionlock:
    def test_clear_versionlock_plugin_not_enabled(self, caplog, monkeypatch):
        monkeypatch.setattr(os.path, "isfile", mock.Mock(return_value=False))
        monkeypatch.setattr(os.path, "getsize", mock.Mock(return_value=0))

        pkghandler.clear_versionlock()

        assert len(caplog.records) == 1
        assert caplog.records[-1].message == "Usage of YUM/DNF versionlock plugin not detected."

    def test_clear_versionlock_user_says_yes(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(utils, "ask_to_continue", mock.Mock())
        monkeypatch.setattr(os.path, "isfile", mock.Mock(return_value=True))
        monkeypatch.setattr(os.path, "getsize", mock.Mock(return_value=1))
        monkeypatch.setattr(pkgmanager, "call_yum_cmd", CallYumCmdMocked())
        monkeypatch.setattr(RestorableFile, "enable", mock.Mock())
        monkeypatch.setattr(RestorableFile, "restore", mock.Mock())

        pkghandler.clear_versionlock()

        assert pkgmanager.call_yum_cmd.call_count == 1
        assert pkgmanager.call_yum_cmd.command == "versionlock"
        assert pkgmanager.call_yum_cmd.args == ["clear"]
        assert len(global_backup_control._restorables) == 1

    def test_clear_versionlock_user_says_no(self, monkeypatch):
        monkeypatch.setattr(
            utils, "ask_to_continue", SysExitCallableObject(msg="User said no", spec=utils.ask_to_continue)
        )
        monkeypatch.setattr(os.path, "isfile", mock.Mock(return_value=True))
        monkeypatch.setattr(os.path, "getsize", mock.Mock(return_value=1))
        monkeypatch.setattr(pkgmanager, "call_yum_cmd", CallYumCmdMocked())

        with pytest.raises(SystemExit):
            pkghandler.clear_versionlock()

        assert not pkgmanager.call_yum_cmd.called


class TestGetRpmHeader:
    @pytest.mark.skipif(
        not is_rpm_based_os(),
        reason="Current test runs only on rpm based systems.",
    )
    def test_get_rpm_header(self, monkeypatch):
        monkeypatch.setattr(rpm, "TransactionSet", FakeTransactionSet)
        pkg = create_pkg_obj(name="pkg1", version="1", release="2")

        hdr = pkghandler.get_rpm_header(pkg)

        assert hdr == {
            rpm.RPMTAG_NAME: "pkg1",
            rpm.RPMTAG_VERSION: "1",
            rpm.RPMTAG_RELEASE: "2",
            rpm.RPMTAG_EVR: "1-2",
        }

    def test_get_rpm_header_failure(self, monkeypatch):
        monkeypatch.setattr(rpm, "TransactionSet", FakeTransactionSet)
        unknown_pkg = create_pkg_obj(name="unknown", version="1", release="1")

        with pytest.raises(SystemExit):
            pkghandler.get_rpm_header(unknown_pkg)


class TestPreserveOnlyRHELKernel:
    @centos7
    def test_preserve_only_rhel_kernel(self, pretend_os, monkeypatch):
        monkeypatch.setattr(pkghandler, "install_rhel_kernel", lambda: True)
        monkeypatch.setattr(pkghandler, "fix_invalid_grub2_entries", lambda: None)
        monkeypatch.setattr(pkghandler, "remove_non_rhel_kernels", mock.Mock(return_value=[]))
        monkeypatch.setattr(pkghandler, "install_gpg_keys", mock.Mock())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_by_fingerprint",
            GetInstalledPkgsByFingerprintMocked(return_value=[create_pkg_information(name="kernel")]),
        )
        monkeypatch.setattr(system_info, "name", "CentOS7")
        monkeypatch.setattr(system_info, "arch", "x86_64")
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())

        pkghandler.preserve_only_rhel_kernel()

        assert utils.run_subprocess.cmd == ["yum", "update", "-y", "--releasever=7Server", "kernel"]
        assert pkghandler.get_installed_pkgs_by_fingerprint.call_count == 1


class TestGetKernelAvailability:
    @pytest.mark.parametrize(
        ("subprocess_output", "expected_installed", "expected_available"),
        (
            (
                YUM_KERNEL_LIST_OLDER_AVAILABLE,
                ["4.7.4-200.fc24"],
                ["4.5.5-300.fc24", "4.7.2-201.fc24", "4.7.4-200.fc24"],
            ),
            (YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE, ["4.7.4-200.fc24"], ["4.7.4-200.fc24"]),
            (
                YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED,
                ["4.7.2-201.fc24", "4.7.4-200.fc24"],
                ["4.7.4-200.fc24"],
            ),
        ),
    )
    @centos7
    def test_get_kernel_availability(
        self, pretend_os, subprocess_output, expected_installed, expected_available, monkeypatch
    ):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output))

        installed, available = pkghandler.get_kernel_availability()

        assert installed == expected_installed
        assert available == expected_available


class TestHandleNoNewerRHELKernelAvailable:
    @centos7
    def test_handle_older_rhel_kernel_available(self, pretend_os, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=YUM_KERNEL_LIST_OLDER_AVAILABLE))

        pkghandler.handle_no_newer_rhel_kernel_available()

        assert utils.run_subprocess.cmd == ["yum", "install", "-y", "--releasever=7Server", "kernel-4.7.2-201.fc24"]

    @centos7
    def test_handle_older_rhel_kernel_not_available(self, pretend_os, monkeypatch):
        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_string=YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE)
        )
        monkeypatch.setattr(pkghandler, "replace_non_rhel_installed_kernel", mock.Mock())

        pkghandler.handle_no_newer_rhel_kernel_available()

        assert pkghandler.replace_non_rhel_installed_kernel.call_count == 1

    @centos7
    def test_handle_older_rhel_kernel_not_available_multiple_installed(self, pretend_os, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            RunSubprocessMocked(return_string=YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE_MULTIPLE_INSTALLED),
        )
        monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())

        pkghandler.handle_no_newer_rhel_kernel_available()

        assert len(utils.remove_pkgs.pkgs) == 1
        assert utils.remove_pkgs.pkgs[0] == "kernel-4.7.4-200.fc24"
        assert utils.run_subprocess.cmd == ["yum", "install", "-y", "--releasever=7Server", "kernel-4.7.4-200.fc24"]


class TestReplaceNonRHELInstalledKernel:
    def test_replace_non_rhel_installed_kernel_rhsm_repos(self, monkeypatch):
        monkeypatch.setattr(system_info, "submgr_enabled_repos", ["enabled_rhsm_repo"])
        monkeypatch.setattr(utils, "ask_to_continue", mock.Mock())
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        version = "4.7.4-200.fc24"

        pkghandler.replace_non_rhel_installed_kernel(version)

        assert utils.download_pkg.call_count == 1
        assert utils.download_pkg.pkg == "kernel-4.7.4-200.fc24"
        assert utils.download_pkg.enable_repos == ["enabled_rhsm_repo"]
        assert utils.run_subprocess.cmd == [
            "rpm",
            "-i",
            "--force",
            "--nodeps",
            "--replacepkgs",
            "%skernel-4.7.4-200.fc24*" % utils.TMP_DIR,
        ]

    def test_replace_non_rhel_installed_kernel_custom_repos(self, monkeypatch):
        monkeypatch.setattr(system_info, "submgr_enabled_repos", [])
        monkeypatch.setattr(tool_opts, "enablerepo", ["custom_repo"])
        monkeypatch.setattr(tool_opts, "no_rhsm", True)
        monkeypatch.setattr(utils, "ask_to_continue", mock.Mock())
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        version = "4.7.4-200.fc24"

        pkghandler.replace_non_rhel_installed_kernel(version)

        assert utils.download_pkg.enable_repos == ["custom_repo"]

    @pytest.mark.parametrize(
        ("download_pkg_return", "subprocess_return_code"),
        (
            (None, 0),
            ("/path/to.rpm", 1),
        ),
        ids=(
            "Unable to download the kernel",
            "",
        ),
    )
    def test_replace_non_rhel_installed_kernel_failing(self, download_pkg_return, subprocess_return_code, monkeypatch):
        monkeypatch.setattr(utils, "ask_to_continue", mock.Mock())
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked(return_value=download_pkg_return))
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=subprocess_return_code))
        version = "4.7.4-200.fc24"

        with pytest.raises(SystemExit):
            pkghandler.replace_non_rhel_installed_kernel(version)


class TestGetKernel:
    def test_get_kernel(self):
        kernel_version = list(pkghandler.get_kernel(YUM_KERNEL_LIST_OLDER_NOT_AVAILABLE))

        assert kernel_version == ["4.7.4-200.fc24", "4.7.4-200.fc24"]


class TestVerifyRHELKernelInstalled:
    def test_verify_rhel_kernel_installed(self, monkeypatch):
        monkeypatch.setattr(pkghandler, "is_rhel_kernel_installed", lambda: True)

        pkghandler.verify_rhel_kernel_installed()

    def test_verify_rhel_kernel_installed_not_installed(self, monkeypatch):
        monkeypatch.setattr(pkghandler, "is_rhel_kernel_installed", lambda: False)

        with pytest.raises(SystemExit):
            pkghandler.verify_rhel_kernel_installed()


class TestIsRHELKernelInstalled:
    def test_is_rhel_kernel_installed_no(self, monkeypatch):
        monkeypatch.setattr(pkghandler, "get_installed_pkgs_by_fingerprint", lambda x, name: [])

        assert not pkghandler.is_rhel_kernel_installed()

    def test_is_rhel_kernel_installed_yes(self, monkeypatch):
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_by_fingerprint",
            GetInstalledPkgsByFingerprintMocked(return_value=[create_pkg_information(name="kernel")]),
        )

        assert pkghandler.is_rhel_kernel_installed()


class TestFixInvalidGrub2Entries:
    @pytest.mark.parametrize(
        ("version", "arch"),
        (
            (Version(7, 0), "x86_64"),
            (Version(8, 0), "s390x"),
        ),
    )
    def test_fix_invalid_grub2_entries_not_applicable(self, version, arch, caplog, monkeypatch):
        monkeypatch.setattr(system_info, "version", version)
        monkeypatch.setattr(system_info, "arch", arch)

        pkghandler.fix_invalid_grub2_entries()

        assert not [r for r in caplog.records if r.levelname != "DEBUG"]

    def test_fix_invalid_grub2_entries(self, caplog, monkeypatch):
        monkeypatch.setattr(system_info, "version", Version(8, 0))
        monkeypatch.setattr(system_info, "arch", "x86_64")
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda x: "1b11755afe1341d7a86383ca4944c324\n",
        )
        monkeypatch.setattr(
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
        monkeypatch.setattr(os, "remove", mock.Mock())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        pkghandler.fix_invalid_grub2_entries()

        assert os.remove.call_count == 3
        assert utils.run_subprocess.call_count == 2


class TestFixDefaultKernel:
    @pytest.mark.parametrize(
        ("system_name", "version", "old_kernel", "new_kernel", "not_default_kernels"),
        (
            (
                "Oracle Linux Server release 7.9",
                Version(7, 9),
                "kernel-uek",
                "kernel",
                ("kernel-uek", "kernel-core"),
            ),
            (
                "Oracle Linux Server release 8.1",
                Version(8, 1),
                "kernel-uek",
                "kernel-core",
                ("kernel-uek", "kernel"),
            ),
            (
                "CentOS Plus Linux Server release 7.9",
                Version(7, 9),
                "kernel-plus",
                "kernel",
                ("kernel-plus",),
            ),
        ),
    )
    def test_fix_default_kernel_converting_success(
        self, system_name, version, old_kernel, new_kernel, not_default_kernels, caplog, monkeypatch
    ):
        monkeypatch.setattr(system_info, "name", system_name)
        monkeypatch.setattr(system_info, "arch", "x86_64")
        monkeypatch.setattr(system_info, "version", version)
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=%s\n" % old_kernel,
        )
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())

        pkghandler.fix_default_kernel()

        warning_msgs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warning_msgs
        assert "Detected leftover boot kernel, changing to RHEL kernel" in warning_msgs[-1].message

        (filename, content), _dummy = utils.store_content_to_file.call_args
        kernel_file_lines = content.splitlines()

        assert "/etc/sysconfig/kernel" == filename
        assert "DEFAULTKERNEL=%s" % new_kernel in kernel_file_lines

        for kernel_name in not_default_kernels:
            assert "DEFAULTKERNEL=%s" % kernel_name not in kernel_file_lines

    def test_fix_default_kernel_with_no_incorrect_kernel(self, caplog, monkeypatch):
        monkeypatch.setattr(system_info, "name", "CentOS Plus Linux Server release 7.9")
        monkeypatch.setattr(system_info, "arch", "x86_64")
        monkeypatch.setattr(system_info, "version", Version(7, 9))
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=kernel\n",
        )
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())

        pkghandler.fix_default_kernel()

        info_records = [m for m in caplog.records if m.levelname == "INFO"]
        warning_records = [m for m in caplog.records if m.levelname == "WARNING"]
        debug_records = [m for m in caplog.records if m.levelname == "DEBUG"]

        assert not warning_records
        assert any("Boot kernel validated." in r.message for r in debug_records)

        for record in info_records:
            assert not re.search("Boot kernel [^ ]\\+ was changed to [^ ]\\+", record.message)


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
            re.escape(
                "The arches ('aarch64' and 'i86') do not match. Can only compare versions for the same arches. There is an architecture mismatch likely due to incorrectly defined repositories on the system."
            ),
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
    ("package_manager_type", "packages", "expected"),
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
        ),
        (
            "yum",
            [
                "convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
                "convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",
            ],
            frozenset(("convert2rhel.noarch-0.24-1.20211111151554764702.pr356.28.ge9ed160.el8",)),
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
        ),
    ),
)
@centos8
def test_get_total_packages_to_update(
    package_manager_type,
    packages,
    expected,
    pretend_os,
    monkeypatch,
):
    monkeypatch.setattr(pkgmanager, "TYPE", package_manager_type)
    if package_manager_type == "dnf":
        monkeypatch.setattr(
            pkghandler,
            "_get_packages_to_update_%s" % package_manager_type,
            value=lambda disable_repos: packages,
        )
    else:
        monkeypatch.setattr(
            pkghandler,
            "_get_packages_to_update_%s" % package_manager_type,
            value=lambda disable_repos: packages,
        )
    assert get_total_packages_to_update() == expected


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
    ("packages",),
    (
        (["package-1", "package-2", "package-i3"],),
        (["package-1"],),
    ),
)
@all_systems
def test_get_packages_to_update_dnf(packages, pretend_os, monkeypatch):
    dummy_mock = mock.Mock()
    PkgName = namedtuple("PkgNames", ["name"])
    transaction_pkgs = [PkgName(package) for package in packages]

    monkeypatch.setattr(pkgmanager.Base, "read_all_repos", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "fill_sack", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "upgrade_all", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "resolve", value=dummy_mock)
    monkeypatch.setattr(pkgmanager.Base, "transaction", value=transaction_pkgs)

    assert _get_packages_to_update_dnf() == packages


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
def test_get_packages_to_update_dnf_rhel_repos(monkeypatch):
    # Mock the uneccesary calls for testing
    monkeypatch.setattr(pkgmanager.Base, "fill_sack", value=mock.Mock())
    monkeypatch.setattr(pkgmanager.Base, "upgrade_all", value=mock.Mock())
    monkeypatch.setattr(pkgmanager.Base, "resolve", value=mock.Mock())
    monkeypatch.setattr(pkgmanager.Base, "transaction", value=[])

    rhel_repo_id = "rhel-8-for-x86_64-baseos-rpms"

    # Create DNF Base object
    base = pkgmanager.Base()

    # Add RHEL repo to the DNF Base
    base.repos.add_new_repo(rhel_repo_id, base.conf, baseurl="https://random.testing.url/")

    # Get all enabled repos in the current system
    base.read_all_repos()
    enabled_repos = [repo.id for repo in base.repos.iter_enabled()]

    # Check if the list is not empty and the RHEL repo is enabled
    assert enabled_repos
    assert rhel_repo_id in enabled_repos

    # Choose one of the enabled repos on the system
    # Avoid getting the rhel_repo_id if on 0 index, then get the repo id from 1.
    # By this is checked if disabling one of the user provided repos is working. We need
    # repo which is present on the system and is different from the rhel one.
    # This allows us to simulate the situation. One of the system repos that is different from the rhel
    # one is used.
    repo_for_disable = [enabled_repos[0]] if enabled_repos[0] != rhel_repo_id else [enabled_repos[1]]

    # Add the rhel* to the repo for disable
    repo_for_disable += ["rhel*"]

    # Patch the original Dnf Base to ours to have access to it and contain the added repo
    monkeypatch.setattr(pkgmanager, "Base", mock.Mock(return_value=base))

    _get_packages_to_update_dnf(disable_repos=repo_for_disable)

    # Get enabled repos after the _get_packages_to_update_dnf where the RHEL repos are disabled
    enabled_repos = [repo.id for repo in base.repos.iter_enabled()]

    assert rhel_repo_id not in enabled_repos
    assert repo_for_disable not in enabled_repos


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
def test_get_packages_to_update_yum_rhel_repos(monkeypatch):
    class MockPkgList:
        """Class for mocking the doPackageList and having the needed attributes."""

        def __init__(self, pkgnarrow):
            self.updates = []
            assert pkgnarrow == "updates"

    # Mock unnecessary calls for testing
    monkeypatch.setattr(pkgmanager.YumBase, "doPackageLists", value=MockPkgList)

    # Create YUM Base object to have access to it
    base = pkgmanager.YumBase()

    # Add RHEL repo to the YUM Base
    rhel_repo_id = "rhel-7-server-rpms"
    base.repos.add(pkgmanager.repos.Repository(rhel_repo_id))
    base.repos.enableRepo(rhel_repo_id)

    # Get all enabled repos in the current system
    enabled_repos = [repo.id for repo in base.repos.listEnabled()]

    # Check if the list is not empty and the RHEL repo is enabled
    assert enabled_repos
    assert rhel_repo_id in enabled_repos

    # Choose one of the enabled repos on the system
    # Avoid getting the rhel_repo_id if on 0 index, then get the repo id from 1.
    # By this is checked if disabling one of the user provided repos is working. We need
    # repo which is present on the system and is different from the rhel one.
    # This allows us to simulate the situation. One of the system repos that is different from the rhel
    # one is used.
    repo_for_disable = [enabled_repos[0]] if enabled_repos[0] != rhel_repo_id else [enabled_repos[1]]

    # Add the rhel* to the repo for disable
    repo_for_disable += ["rhel*"]

    # Patch the original YUM Base to ours to have access to it and contain the added repo
    monkeypatch.setattr(pkgmanager, "YumBase", mock.Mock(return_value=base))

    # Call the function to be tested
    _get_packages_to_update_yum(disable_repos=repo_for_disable)

    # Get enabled repos after the call where the RHEL repos are disabled
    enabled_repos = [repo.id for repo in base.repos.listEnabled()]

    assert rhel_repo_id not in enabled_repos
    assert repo_for_disable not in enabled_repos


class TestInstallGpgKeys:
    data_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "../data/version-independent"))
    gpg_keys_dir = os.path.join(data_dir, "gpg-keys")

    def test_install_gpg_keys(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(utils, "DATA_DIR", self.data_dir)

        # Prevent RestorableRpmKey from actually performing any work
        monkeypatch.setattr(RestorableRpmKey, "enable", mock.Mock())

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
                    arch=".(none)",
                    fingerprint="none",
                    signature="(none)",
                )
            ],
            [],
        ),
    ),
)
@centos7
def test_get_system_packages_for_replacement(pretend_os, pkgs, expected, monkeypatch):
    monkeypatch.setattr(
        pkghandler, "get_installed_pkg_information", GetInstalledPkgInformationMocked(return_value=pkgs)
    )
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
    monkeypatch.setattr(
        pkgmanager.rpmsack.RPMDBPackageSack,
        "returnPackages",
        ReturnPackagesObject(spec=pkgmanager.rpmsack.RPMDBPackageSack.returnPackages),
    )
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
    monkeypatch.setattr(pkgmanager.query, "Query", FakeDnfQuery)
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
    monkeypatch.setattr(
        pkghandler, "get_installed_pkg_information", GetInstalledPkgInformationMocked(return_value=package)
    )
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
    monkeypatch.setattr(
        pkghandler, "get_installed_pkg_information", GetInstalledPkgInformationMocked(return_value=package)
    )
    pkgs_by_fingerprint = pkghandler.get_installed_pkgs_by_fingerprint("non-existing fingerprint")

    assert not pkgs_by_fingerprint


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
@centos7
def test_format_pkg_info_yum(pretend_os, monkeypatch):
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

    result = pkghandler.format_pkg_info(packages)
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
def test_format_pkg_info_dnf(pretend_os, monkeypatch):
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

    result = pkghandler.format_pkg_info(packages)

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


def different_fingerprints_for_packages_to_remove(fingerprints, name=""):
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
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(side_effect=different_fingerprints_for_packages_to_remove),
    )
    original_func = pkghandler.get_packages_to_remove.__wrapped__
    monkeypatch.setattr(pkghandler, "get_packages_to_remove", mock_decorator(original_func))

    result = pkghandler.get_packages_to_remove(["installed_pkg", "not_installed_pkg"])
    assert len(result) == 1
    assert result[0].nevra.name == "installed_pkg"


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
    monkeypatch.setattr(utils, "ask_to_continue", mock.Mock())
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
    monkeypatch.setattr(system_info, "fingerprints_orig_os", fingerprint_orig_os)
    monkeypatch.setattr(
        pkghandler, "get_installed_pkg_information", GetInstalledPkgInformationMocked(pkg_selection="fingerprints")
    )

    pkgs = pkghandler.get_third_party_pkgs()

    assert pkghandler.format_pkg_info.call_count == expected_count
    assert len(pkgs) == expected_pkgs


def test_list_non_red_hat_pkgs_left(monkeypatch):
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
    monkeypatch.setattr(
        pkghandler, "get_installed_pkg_information", GetInstalledPkgInformationMocked(pkg_selection="fingerprints")
    )
    pkghandler.list_non_red_hat_pkgs_left()

    assert len(pkghandler.format_pkg_info.call_args[0][0]) == 1
    assert pkghandler.format_pkg_info.call_args[0][0][0].nevra.name == "pkg2"


@pytest.mark.parametrize(
    (
        "subprocess_output",
        "is_only_rhel_kernel",
        "expected",
    ),
    (
        ("Package kernel-3.10.0-1127.19.1.el7.x86_64 already installed and latest version", True, False),
        ("Package kernel-3.10.0-1127.19.1.el7.x86_64 already installed and latest version", False, True),
        ("Installed:\nkernel", False, False),
    ),
    ids=(
        "Kernels collide and installed is already RHEL. Do not update.",
        "Kernels collide and installed is not RHEL and older. Update.",
        "Kernels do not collide. Install RHEL kernel and do not update.",
    ),
)
@centos7
def test_install_rhel_kernel(subprocess_output, is_only_rhel_kernel, expected, pretend_os, monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output))
    monkeypatch.setattr(pkghandler, "handle_no_newer_rhel_kernel_available", mock.Mock())

    if is_only_rhel_kernel:
        pkg_selection = "empty"
    else:
        pkg_selection = "kernels"

    monkeypatch.setattr(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection=pkg_selection),
    )

    update_kernel = pkghandler.install_rhel_kernel()

    assert update_kernel is expected


@pytest.mark.parametrize(
    ("subprocess_output",),
    (
        ("Package kernel-2.6.32-754.33.1.el7.x86_64 already installed and latest version",),
        ("Package kernel-4.18.0-193.el8.x86_64 is already installed.",),
    ),
)
@centos7
def test_install_rhel_kernel_already_installed_regexp(subprocess_output, pretend_os, monkeypatch):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output))
    monkeypatch.setattr(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection="kernels"),
    )

    pkghandler.install_rhel_kernel()

    assert pkghandler.get_installed_pkgs_w_different_fingerprint.call_count == 1


def test_remove_non_rhel_kernels(monkeypatch):
    monkeypatch.setattr(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection="kernels"),
    )
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
    monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())

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
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection="kernels"),
    )
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
    monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())
    monkeypatch.setattr(pkgmanager, "call_yum_cmd", CallYumCmdMocked())

    removed_pkgs = pkghandler.remove_non_rhel_kernels()
    pkghandler.install_additional_rhel_kernel_pkgs(removed_pkgs)
    assert pkgmanager.call_yum_cmd.call_count == 2


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
        pytest.param(
            "gpg-pubkey",
            "C2R Fedora (37) <fedora-37-primary@fedoraproject.org>&(none)&gpg-pubkey-0:5323552a-6112bcdc.(none)&(none)",
            [
                PackageInformation(
                    packager="Fedora (37) <fedora-37-primary@fedoraproject.org>",
                    vendor="(none)",
                    nevra=PackageNevra(
                        name="gpg-pubkey",
                        epoch="0",
                        version="5323552a",
                        release="6112bcdc",
                        arch=None,
                    ),
                    fingerprint="none",
                    signature="(none)",
                )
            ],
            [
                "rpm",
                "--qf",
                "C2R %{PACKAGER}&%{VENDOR}&%{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}&%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{%|SIGGPG?{%{SIGGPG:pgpsig}}:{%|SIGPGP?{%{SIGPGP:pgpsig}}:{(none)}|}|}|}|\n",
                "-q",
                "gpg-pubkey",
            ],
            id="gpg-pubkey case with .(none) as arch",
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
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output))

    result = pkghandler.get_installed_pkg_information(package_name)
    assert utils.run_subprocess.cmd == expected_command
    assert result == expected


def test_get_installed_pkg_information_value_error(monkeypatch, caplog):
    output = "C2R Fedora Project&Fedora Project&fonts-filesystem-a:aabb.d.1-l.fc37.noarch&RSA/SHA256, Tue 23 Aug 2022 08:06:00 -03, Key ID f55ad3fb5323552a"
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=output))

    result = pkghandler.get_installed_pkg_information()
    assert not result
    assert "Failed to parse a package" in caplog.records[-1].message


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
            ["2:eog-44.1-1.fc38.x86_64", "2:gnome-backgrounds-44.0-1.fc38.noarch", "2:gnome-maps-44.1-1.fc38.x86_64"],
            """\
                C2R 2:eog-44.1-1.fc38.x86_64&updates
                C2R 2:gnome-backgrounds-44.0-1.fc38.noarch&fedora
                C2R 2:gnome-maps-44.1-1.fc38.x86_64&updates
            """,
            {
                "2:eog-44.1-1.fc38.x86_64": "updates",
                "2:gnome-backgrounds-44.0-1.fc38.noarch": "fedora",
                "2:gnome-maps-44.1-1.fc38.x86_64": "updates",
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
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output))

    result = pkghandler._get_package_repositories(packages)
    assert expected_result == result
    if caplog.records[-1].message:
        assert "Got a line without the C2R identifier" in caplog.records[-1].message


@centos7
def test_get_package_repositories_repoquery_failure(pretend_os, monkeypatch, caplog):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=1, return_string="failed"))

    packages = ["0:gnome-backgrounds-44.0-1.fc38.noarch", "0:eog-44.1-1.fc38.x86_64", "0:gnome-maps-44.1-1.fc38.x86_64"]
    result = pkghandler._get_package_repositories(packages)

    assert "Repoquery exited with return code 1 and with output: failed" in caplog.records[-1].message
    for package, repo in result.items():
        assert package in packages
        assert repo == "N/A"
