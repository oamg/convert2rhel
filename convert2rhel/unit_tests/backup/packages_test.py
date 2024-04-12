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

from convert2rhel import exceptions, pkghandler, pkgmanager, unit_tests, utils
from convert2rhel.backup import packages
from convert2rhel.backup.packages import RestorablePackage, RestorablePackageSet
from convert2rhel.systeminfo import Version
from convert2rhel.unit_tests import (
    CallYumCmdMocked,
    DownloadPkgMocked,
    GetInstalledPkgInformationMocked,
    MockFunctionObject,
    RemovePkgsMocked,
    RunSubprocessMocked,
    StoreContentToFileMocked,
)
from convert2rhel.unit_tests.conftest import centos7


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


class TestRestorablePackage:
    def test_install_local_rpms_with_empty_list(self, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp._backedup_pkgs_paths = ["test.rpm"]

        assert rp._install_local_rpms()
        assert utils.run_subprocess.call_count == 1
        assert ["rpm", "-i", "test.rpm"] == utils.run_subprocess.cmd

    def test_install_local_rpms_with_replace(self, monkeypatch):
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp._backedup_pkgs_paths = ["test.rpm"]

        assert rp._install_local_rpms(replace=True)
        assert utils.run_subprocess.call_count == 1
        assert ["rpm", "-i", "--replacepkgs", "test.rpm"] == utils.run_subprocess.cmd

    def test_install_local_rpms_without_path(self, caplog):
        rp = RestorablePackage(pkgs=["test.rpm"])
        assert not rp._install_local_rpms()
        assert "No package to install." in caplog.records[-1].message

    def test_enable(self, monkeypatch, tmpdir, global_backup_control):
        monkeypatch.setattr(packages, "BACKUP_DIR", str(tmpdir))
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked())
        pkgs = ["pkg1", "pkg2", "pkg3"]
        rp = RestorablePackage(pkgs=pkgs)
        global_backup_control.push(rp)

        assert utils.download_pkg.call_count == len(pkgs)
        assert len(global_backup_control._restorables) == 1
        assert len(rp._backedup_pkgs_paths) == len(pkgs)

    def test_enable_eus_systems(self, monkeypatch, tmpdir, global_system_info):
        monkeypatch.setattr(packages, "BACKUP_DIR", str(tmpdir))
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked())
        monkeypatch.setattr(packages, "system_info", global_system_info)

        packages.system_info.eus_system = True
        packages.system_info.id = "centos"

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp._backedup_pkgs_paths = ["test.rpm"]
        rp.enable()

        assert utils.download_pkg.call_count == 1

    def test_package_already_enabled(self, monkeypatch, tmpdir):
        monkeypatch.setattr(packages, "BACKUP_DIR", str(tmpdir))
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked())

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp.enable()
        assert utils.download_pkg.call_count == 1

        rp.enable()
        # Assert that we are still at call_count 1 meaning that we returning
        # earlier without going through the backup.
        assert utils.download_pkg.call_count == 1

    def test_restore(self, monkeypatch):
        monkeypatch.setattr(
            packages.RestorablePackage,
            "_install_local_rpms",
            value=mock.Mock(),
        )
        monkeypatch.setattr(utils, "remove_orphan_folders", value=mock.Mock())

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp.enabled = True
        rp._backedup_pkgs_paths = ["test.rpm"]
        rp.restore()
        assert utils.remove_orphan_folders.call_count == 1
        assert rp._install_local_rpms.call_count == 1

    def test_restore_pkg_without_path(self, monkeypatch, caplog):
        monkeypatch.setattr(utils, "remove_orphan_folders", value=mock.Mock())

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp.enabled = True
        rp.restore()
        assert utils.remove_orphan_folders.call_count == 1
        assert "Couldn't find a backup for test.rpm package." in caplog.records[-1].message

    def test_restore_second_restore(self, monkeypatch):
        monkeypatch.setattr(
            packages.RestorablePackage,
            "_install_local_rpms",
            value=mock.Mock(),
        )
        monkeypatch.setattr(utils, "remove_orphan_folders", value=mock.Mock())

        rp = RestorablePackage(pkgs=["test.rpm"])
        rp.enabled = True
        rp._backedup_pkgs_paths = ["test.rpm"]
        rp.restore()
        assert utils.remove_orphan_folders.call_count == 1
        assert rp._install_local_rpms.call_count == 1

        rp.restore()
        assert utils.remove_orphan_folders.call_count == 1
        assert rp._install_local_rpms.call_count == 1

    def test_restorable_package_backup_without_dir(self, monkeypatch, tmpdir, caplog):
        backup_dir = str(tmpdir.join("non-existing"))
        monkeypatch.setattr(packages, "BACKUP_DIR", backup_dir)
        rp = RestorablePackage(pkgs=["pkg-1"])
        rp.enable()

        assert "Can't access %s" % backup_dir in caplog.records[-1].message

    def test_install_local_rpms_package_install_warning(self, monkeypatch, caplog):
        pkg_name = "pkg-1"
        run_subprocess_mock = RunSubprocessMocked(
            side_effect=unit_tests.run_subprocess_side_effect(
                (("rpm", "-i", pkg_name), ("test", 1)),
            )
        )
        monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess_mock)

        rp = RestorablePackage(pkgs=[pkg_name])
        rp._backedup_pkgs_paths = pkg_name
        result = rp._install_local_rpms(replace=False, critical=False)

        assert result == False
        assert run_subprocess_mock.call_count == 1
        assert "Couldn't install %s packages." % pkg_name in caplog.records[-1].message

    def test_test_install_local_rpms_system_exit(self, monkeypatch, caplog):
        pkg_name = "pkg-1"
        run_subprocess_mock = RunSubprocessMocked(
            side_effect=unit_tests.run_subprocess_side_effect(
                (("rpm", "-i", pkg_name), ("test", 1)),
            )
        )
        monkeypatch.setattr(
            utils,
            "run_subprocess",
            value=run_subprocess_mock,
        )

        rp = RestorablePackage(pkgs=[pkg_name])
        rp._backedup_pkgs_paths = pkg_name
        with pytest.raises(exceptions.CriticalError):
            rp._install_local_rpms(replace=False, critical=True)

        assert run_subprocess_mock.call_count == 1
        assert "Error: Couldn't install %s packages." % pkg_name in caplog.records[-1].message


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
        ubi9_repo_path = yum_repo_dir.join("ubi_9.repo")

        monkeypatch.setattr(packages, "_SUBMGR_RPMS_DIR", str(pkg_download_dir))
        monkeypatch.setattr(packages, "_RHSM_TMP_DIR", str(yum_repo_dir))
        monkeypatch.setattr(packages, "_UBI_7_REPO_PATH", str(ubi7_repo_path))
        monkeypatch.setattr(packages, "_UBI_8_REPO_PATH", str(ubi8_repo_path))
        monkeypatch.setattr(packages, "_UBI_9_REPO_PATH", str(ubi9_repo_path))

        return RestorablePackageSet(["subscription-manager", "python-syspurpose"])

    @pytest.mark.parametrize(
        ("pkgs_to_install", "pkgs_to_update", "reposdir"),
        (
            (["pkg-1"], [], None),
            (["pkg-1"], [], "test-dir"),
            ([], ["pkg-1"], None),
            ([], [], "test-dir"),
            (["pkg-1"], ["pkg-2"], None),
        ),
    )
    def test_smoketest_init(self, pkgs_to_install, pkgs_to_update, reposdir):
        package_set = RestorablePackageSet(pkgs_to_install, pkgs_to_update, reposdir)

        assert package_set.pkgs_to_install == pkgs_to_install
        assert package_set.pkgs_to_update == pkgs_to_update
        assert package_set.reposdir == reposdir

        assert package_set.enabled is False
        # We actually care that this is an empty list and not just False-y
        assert package_set.installed_pkgs == []  # pylint: disable=use-implicit-booleaness-not-comparison

    @pytest.mark.parametrize(
        ("major", "minor"),
        (
            (7, 10),
            (8, 5),
            (9, 3),
        ),
    )
    def test_enable_need_to_install(self, major, minor, package_set, global_system_info, caplog, monkeypatch, tmpdir):
        repofile = tmpdir.join("repofile.repo")
        global_system_info.version = Version(major, minor)
        monkeypatch.setattr(packages, "system_info", global_system_info)
        monkeypatch.setattr(packages, "_UBI_REPO_MAPPING", {major: (str(repofile), "test")})
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

    @centos7
    def test_enable_call_yum_cmd_fail(self, pretend_os, package_set, caplog, monkeypatch, tmpdir):
        repofile = tmpdir.join("repofile.repo")
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkg_information",
            GetInstalledPkgInformationMocked(side_effect=(["subscription-manager"], [], [])),
        )
        monkeypatch.setattr(utils, "download_pkg", DownloadPkgMocked(side_effect=self.fake_download_pkg))
        monkeypatch.setattr(packages, "_UBI_REPO_MAPPING", {7: (str(repofile), "test")})
        monkeypatch.setattr(pkgmanager, "call_yum_cmd", CallYumCmdMocked(return_code=1))
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
        monkeypatch.setattr(utils, "remove_pkgs", mock_remove_pkgs)
        package_set.enabled = 1
        package_set.installed_pkgs = ["one", "two"]

        package_set.restore()

        assert mock_remove_pkgs.call_count == 1
        mock_remove_pkgs.assert_called_with(["one", "two"], critical=False)

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
        monkeypatch.setattr(utils, "remove_pkgs", remove_pkgs_mock)

        package_set.enabled = 1
        package_set.installed_pkgs = install
        package_set.updated_pkgs = update

        package_set.restore()

        remove_pkgs_mock.assert_called_with(removed, critical=False)

    def test_restore_not_enabled(self, package_set, monkeypatch):
        mock_remove_pkgs = RemovePkgsMocked()
        monkeypatch.setattr(utils, "remove_pkgs", mock_remove_pkgs)

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
