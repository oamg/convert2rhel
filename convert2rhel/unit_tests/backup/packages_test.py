# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
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

import os

import pytest
import six

from convert2rhel import exceptions, pkghandler, utils
from convert2rhel.backup import packages
from convert2rhel.backup.packages import RestorablePackageSet
from convert2rhel.systeminfo import Version
from convert2rhel.unit_tests import (
    CallYumCmdMocked,
    DownloadPkgMocked,
    GetInstalledPkgInformationMocked,
    MockFunctionObject,
    RemovePkgsMocked,
    StoreContentToFileMocked,
)
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class DownloadPkgsMocked(MockFunctionObject):
    spec = utils.download_pkgs

    def __init__(self, destdir=None, **kwargs):
        self.destdir = destdir

        self.pkgs = []
        self.dest = None

        if "return_value" not in kwargs:
            kwargs["return_value"] = ["/path/to.rpm"]

        super(DownloadPkgsMocked, self).__init__(**kwargs)

    def __call__(self, pkgs, dest, *args, **kwargs):
        self.pkgs = pkgs
        self.dest = dest
        self.reposdir = kwargs.get("reposdir", None)

        if self.destdir and not os.path.exists(self.destdir):
            os.mkdir(self.destdir, 0o700)

        return super(DownloadPkgsMocked, self).__call__(pkgs, dest, *args, **kwargs)


class TestRestorablePackageSet:
    @staticmethod
    def fake_download_pkg(pkg, *args, **kwargs):
        pkg_to_filename = {
            "subscription-manager": "subscription-manager-1.0-1.el7.noarch.rpm",
            "python-syspurpose": "python-syspurpose-1.2-2.el7.noarch.rpm",
            "json-c.x86_64": "json-c-0.14-1.el7.x86_64.rpm",
            "json-c.i686": "json-c-0.14-1.el7.i686.rpm",
            "json-c": "json-c-0.14-1.el7.x86_64.rpm",
        }

        rpm_path = os.path.join(packages._SUBMGR_RPMS_DIR, pkg_to_filename[pkg])
        with open(rpm_path, "w"):
            # We just need to create this file
            pass

        return rpm_path

    @staticmethod
    def fake_get_pkg_name_from_rpm(path):
        path = path.rsplit("/", 1)[-1]
        return path.rsplit("-", 2)[0]

    @pytest.fixture
    def package_set(self, monkeypatch, tmpdir):
        pkg_download_dir = tmpdir.join("pkg-download-dir")
        yum_repo_dir = tmpdir.join("yum-repo.d")
        ubi7_repo_path = yum_repo_dir.join("ubi_7.repo")
        ubi8_repo_path = yum_repo_dir.join("ubi_8.repo")

        monkeypatch.setattr(packages, "_SUBMGR_RPMS_DIR", str(pkg_download_dir))
        monkeypatch.setattr(packages, "_RHSM_TMP_DIR", str(yum_repo_dir))
        monkeypatch.setattr(packages, "_UBI_7_REPO_PATH", str(ubi7_repo_path))
        monkeypatch.setattr(packages, "_UBI_8_REPO_PATH", str(ubi8_repo_path))

        return RestorablePackageSet(["subscription-manager", "python-syspurpose"])

    def test_smoketest_init(self):
        package_set = RestorablePackageSet(["pkg1"])

        assert package_set.pkg_set == ["pkg1"]
        assert package_set.enabled is False
        # We actually care that this is an empty list and not just False-y
        assert package_set.installed_pkgs == []  # pylint: disable=use-implicit-booleaness-not-comparison

    @pytest.mark.parametrize(
        ("rhel_major_version"),
        (
            (7, 10),
            (8, 5),
        ),
    )
    def test_enable_need_to_install(self, rhel_major_version, package_set, global_system_info, caplog, monkeypatch):
        global_system_info.version = Version(*rhel_major_version)
        monkeypatch.setattr(packages, "system_info", global_system_info)

        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked(side_effect=self.fake_download_pkg))
        monkeypatch.setattr(packages, "call_yum_cmd", CallYumCmdMocked())
        monkeypatch.setattr(utils, "get_package_name_from_rpm", self.fake_get_pkg_name_from_rpm)

        package_set.pkgs_to_update = ["json-c.x86_64"]

        package_set.enable()

        assert package_set.enabled is True
        assert frozenset(("python-syspurpose", "subscription-manager")) == frozenset(package_set.installed_pkgs)

        assert "\nPackages we installed or updated:\n" in caplog.records[-1].message
        assert "python-syspurpose" in caplog.records[-1].message
        assert "subscription-manager" in caplog.records[-1].message
        assert "json-c" in caplog.records[-1].message
        assert "json-c" not in package_set.installed_pkgs
        assert "json-c.x86_64" not in package_set.installed_pkgs

    @centos8
    def test_enable_call_yum_cmd_fail(self, pretend_os, package_set, global_system_info, caplog, monkeypatch):
        global_system_info.version = Version(7, 0)
        monkeypatch.setattr(packages, "system_info", global_system_info)
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_information",
            GetInstalledPkgInformationMocked(side_effect=(["subscription-manager"], [], [])),
        )
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked(side_effect=self.fake_download_pkg))

        yum_cmd = CallYumCmdMocked(return_code=1)
        monkeypatch.setattr(pkghandler, "call_yum_cmd", yum_cmd)
        monkeypatch.setattr(utils, "get_package_name_from_rpm", self.fake_get_pkg_name_from_rpm)

        with pytest.raises(exceptions.CriticalError):
            package_set.enable()

        assert (
            "Failed to install subscription-manager packages. Check the yum output below for details"
            in caplog.records[-1].message
        )

    def test_enable_already_enabled(self, package_set, monkeypatch):
        enable_worker_mock = mock.Mock()
        monkeypatch.setattr(packages.RestorablePackageSet, "_enable", enable_worker_mock)
        package_set.enable()
        previous_number_of_calls = enable_worker_mock.call_count
        package_set.enable()

        assert enable_worker_mock.call_count == previous_number_of_calls

    def test_enable_no_packages(self, package_set, caplog, monkeypatch, global_system_info):
        global_system_info.version = Version(8, 0)
        monkeypatch.setattr(pkghandler, "system_info", global_system_info)

        package_set.pkgs_to_install = []
        package_set.pkgs_to_update = ["python-syspurpose", "json-c.x86_64"]

        package_set.enable()

        assert caplog.records[-1].levelname == "INFO"
        assert "All packages were already installed" in caplog.records[-1].message

    def test_restore(self, package_set, monkeypatch):
        mock_remove_pkgs = RemovePkgsMocked()
        monkeypatch.setattr(packages, "remove_pkgs", mock_remove_pkgs)
        package_set.enabled = 1
        package_set.installed_pkgs = ["one", "two"]

        package_set.restore()

        assert mock_remove_pkgs.call_count == 1
        mock_remove_pkgs.assert_called_with(["one", "two"], backup=False, critical=False)

    @pytest.mark.parametrize(
        ("install", "update", "removed"),
        (
            (
                ["subscription-manager", "python-syspurpose", "json-c.x86_64"],
                ["json-c.i686"],
                ["subscription-manager", "python-syspurpose", "json-c.x86_64"],
            ),
            (
                ["subscription-manager", "python-syspurpose", "json-c.x86_64"],
                ["python-syspurpose"],
                ["subscription-manager", "python-syspurpose", "json-c.x86_64"],
            ),
            (
                ["subscription-manager", "json-c.x86_64"],
                ["python-syspurpose"],
                ["subscription-manager", "json-c.x86_64"],
            ),
            (
                ["subscription-manager", "python-syspurpose"],
                ["json-c.x86_64", "json-c.i686"],
                ["subscription-manager", "python-syspurpose"],
            ),
            (
                ["subscription-manager", "python3-cloud-what"],
                ["json-c.x86_64", "python3-syspurpose"],
                ["subscription-manager", "python3-cloud-what"],
            ),
        ),
    )
    def test_restore_with_pkgs_in_updates(self, install, update, removed, package_set, monkeypatch):
        remove_pkgs_mock = RemovePkgsMocked()
        monkeypatch.setattr(packages, "remove_pkgs", remove_pkgs_mock)

        package_set.enabled = 1
        package_set.installed_pkgs = install
        package_set.updated_pkgs = update

        package_set.restore()

        remove_pkgs_mock.assert_called_with(removed, backup=False, critical=False)

    def test_restore_not_enabled(self, package_set, monkeypatch):
        mock_remove_pkgs = RemovePkgsMocked()
        monkeypatch.setattr(packages, "remove_pkgs", mock_remove_pkgs)

        package_set.enabled = 1
        package_set.restore()
        previously_called = mock_remove_pkgs.call_count

        package_set.restore()

        assert previously_called >= 1
        assert mock_remove_pkgs.call_count == previously_called


class TestDownloadRHSMPkgs:
    def test_download_rhsm_pkgs(self, monkeypatch, tmpdir):
        """Smoketest that download_rhsm_pkgs works in the happy path"""
        download_rpms_directory = tmpdir.join("submgr-downloads")
        monkeypatch.setattr(packages, "_SUBMGR_RPMS_DIR", str(download_rpms_directory))

        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())
        monkeypatch.setattr(utils, "download_pkgs", DownloadPkgsMocked(destdir=str(download_rpms_directory)))

        packages._download_rhsm_pkgs(["testpkg"], "/path/to.repo", "content")

        assert utils.store_content_to_file.call_args == mock.call("/path/to.repo", "content")
        assert utils.download_pkgs.call_count == 1

    def test_download_rhsm_pkgs_one_package_failed_to_download(self, monkeypatch):
        """
        Test that download_rhsm_pkgs() aborts when one of the subscription-manager packages fails to download.
        """
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())
        monkeypatch.setattr(utils, "download_pkgs", DownloadPkgsMocked(return_value=["/path/to.rpm", None]))

        with pytest.raises(exceptions.CriticalError):
            packages._download_rhsm_pkgs(["testpkg"], "/path/to.repo", "content")


@pytest.mark.parametrize(
    ("rpm_paths", "expected"),
    ((["pkg1", "pkg2"], ["pkg1", "pkg2"]),),
)
def test_get_pkg_names_from_rpm_paths(rpm_paths, expected, monkeypatch):
    monkeypatch.setattr(utils, "get_package_name_from_rpm", lambda x: x)
    assert packages._get_pkg_names_from_rpm_paths(rpm_paths) == expected
