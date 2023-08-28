# Copyright(C) 2023 Red Hat, Inc.
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

import pytest
import six

from convert2rhel import actions, pkghandler, pkgmanager, unit_tests
from convert2rhel.actions.pre_ponr_changes import handle_packages
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class PrintPkgInfoMocked(unit_tests.MockFunction):
    def __init__(self, pkgs):
        self.called = 0
        self.pkgs = pkgs

    def __call__(self, pkgs):
        self.called += 1
        return self.pkgs


@pytest.fixture
def list_third_party_packages_instance():
    return handle_packages.ListThirdPartyPackages()


def test_list_third_party_packages_no_packages(list_third_party_packages_instance, monkeypatch, caplog):
    monkeypatch.setattr(pkghandler, "get_third_party_pkgs", lambda: [])

    list_third_party_packages_instance.run()

    assert "No third party packages installed" in caplog.records[-1].message
    assert list_third_party_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


@centos8
def test_list_third_party_packages(list_third_party_packages_instance, pretend_os, monkeypatch, caplog):
    monkeypatch.setattr(pkghandler, "get_third_party_pkgs", unit_tests.GetInstalledPkgsWFingerprintsMocked())
    monkeypatch.setattr(pkghandler, "format_pkg_info", PrintPkgInfoMocked(["pytest", "ruby", "shim"]))
    # actual message display will be a table of the packages with specific details
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="THIRD_PARTY_PACKAGE_DETECTED_MESSAGE",
                message=(
                    "Only packages signed by CentOS Linux are to be replaced. Red Hat support won't be provided"
                    " for the following third party packages:\npkg1-0:None-None.None, pkg2-0:None-None.None, gpg-pubkey-0:1.0.0-1.x86_64"
                ),
            ),
        )
    )

    list_third_party_packages_instance.run()
    assert expected.issuperset(list_third_party_packages_instance.messages)
    assert expected.issubset(list_third_party_packages_instance.messages)
    assert "Only packages signed by" in caplog.records[-2].message
    assert len(pkghandler.format_pkg_info.pkgs) == 3

    assert list_third_party_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


class CommandCallableObject(unit_tests.MockFunction):
    def __init__(self, mock_data):
        self.called = 0
        self.mock_data = mock_data
        self.command = None

    def __call__(self, command):
        self.called += 1
        self.command = command
        return self.mock_data


@pytest.fixture
def remove_excluded_packages_instance():
    return handle_packages.RemoveExcludedPackages()


def test_remove_excluded_packages_all_removed(remove_excluded_packages_instance, monkeypatch):
    pkgs_to_remove = ["shim", "ruby", "kernel-core"]
    pkgs_removed = ["shim", "ruby", "kernel-core"]
    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="EXCLUDED_PACKAGES_REMOVED",
                message="The following packages were removed: kernel-core, ruby, shim",
            ),
        )
    )
    monkeypatch.setattr(system_info, "excluded_pkgs", ["installed_pkg", "not_installed_pkg"])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject(pkgs_removed))
    monkeypatch.setattr(pkghandler, "remove_pkgs_unless_from_redhat", CommandCallableObject(pkgs_to_remove))

    remove_excluded_packages_instance.run()
    assert expected.issuperset(remove_excluded_packages_instance.messages)
    assert expected.issubset(remove_excluded_packages_instance.messages)
    assert pkghandler._get_packages_to_remove.called == 1
    assert pkghandler.remove_pkgs_unless_from_redhat.called == 1
    assert pkghandler._get_packages_to_remove.command == system_info.excluded_pkgs
    assert remove_excluded_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


@centos8
def test_remove_excluded_packages_not_removed(remove_excluded_packages_instance, pretend_os, monkeypatch):
    pkgs_to_remove = unit_tests.GetInstalledPkgsWFingerprintsMocked().get_packages()
    pkgs_removed = ["kernel-core"]
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="EXCLUDED_PACKAGES_NOT_REMOVED",
                message="The following packages were not removed: gpg-pubkey-0:1.0.0-1.x86_64, pkg1-0:None-None.None, pkg2-0:None-None.None",
            ),
        )
    )
    monkeypatch.setattr(system_info, "excluded_pkgs", ["installed_pkg", "not_installed_pkg"])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject(pkgs_to_remove))
    monkeypatch.setattr(pkghandler, "remove_pkgs_unless_from_redhat", CommandCallableObject(pkgs_removed))
    monkeypatch.setattr(pkgmanager, "TYPE", "dnf")
    remove_excluded_packages_instance.run()

    assert expected.issuperset(remove_excluded_packages_instance.messages)
    assert expected.issubset(remove_excluded_packages_instance.messages)
    assert pkghandler._get_packages_to_remove.called == 1
    assert pkghandler.remove_pkgs_unless_from_redhat.called == 1
    assert pkghandler._get_packages_to_remove.command == system_info.excluded_pkgs
    assert remove_excluded_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


def test_remove_excluded_packages_error(remove_excluded_packages_instance, monkeypatch):
    pkgs_removed = ["shim", "ruby", "kernel-core"]
    monkeypatch.setattr(system_info, "excluded_pkgs", [])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject(pkgs_removed))
    monkeypatch.setattr(
        pkghandler, "remove_pkgs_unless_from_redhat", mock.Mock(side_effect=SystemExit("Raising SystemExit"))
    )

    remove_excluded_packages_instance.run()

    unit_tests.assert_actions_result(
        remove_excluded_packages_instance,
        level="ERROR",
        id="EXCLUDED_PACKAGE_REMOVAL_FAILED",
        message="Raising SystemExit",
    )


@pytest.fixture
def remove_repository_files_packages_instance():
    return handle_packages.RemoveRepositoryFilesPackages()


def test_remove_repository_files_packages_all_removed(remove_repository_files_packages_instance, monkeypatch):
    pkgs_to_remove = ["shim", "ruby", "kernel-core"]
    pkgs_removed = ["shim", "ruby", "kernel-core"]
    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="REPOSITORY_FILE_PACKAGES_REMOVED",
                message="The following packages were removed: kernel-core, ruby, shim",
            ),
        )
    )
    monkeypatch.setattr(system_info, "repofile_pkgs", ["installed_pkg", "not_installed_pkg"])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject(pkgs_to_remove))
    monkeypatch.setattr(pkghandler, "remove_pkgs_unless_from_redhat", CommandCallableObject(pkgs_removed))

    remove_repository_files_packages_instance.run()

    assert expected.issuperset(remove_repository_files_packages_instance.messages)
    assert expected.issubset(remove_repository_files_packages_instance.messages)
    assert pkghandler._get_packages_to_remove.called == 1
    assert pkghandler.remove_pkgs_unless_from_redhat.called == 1
    assert pkghandler._get_packages_to_remove.command == system_info.repofile_pkgs
    assert remove_repository_files_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


@centos8
def test_remove_repository_files_packages_not_removed(
    remove_repository_files_packages_instance, pretend_os, monkeypatch
):
    pkgs_to_remove = unit_tests.GetInstalledPkgsWFingerprintsMocked().get_packages()
    pkgs_removed = ["kernel-core"]
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="REPOSITORY_FILE_PACKAGES_NOT_REMOVED",
                message="The following packages were not removed: gpg-pubkey-0:1.0.0-1.x86_64, pkg1-0:None-None.None, pkg2-0:None-None.None",
            ),
        )
    )
    monkeypatch.setattr(system_info, "repofile_pkgs", ["installed_pkg", "not_installed_pkg"])
    monkeypatch.setattr(pkghandler, "_get_packages_to_remove", CommandCallableObject(pkgs_to_remove))
    monkeypatch.setattr(pkgmanager, "TYPE", "dnf")
    monkeypatch.setattr(pkghandler, "remove_pkgs_unless_from_redhat", CommandCallableObject(pkgs_removed))

    remove_repository_files_packages_instance.run()

    assert expected.issuperset(remove_repository_files_packages_instance.messages)
    assert expected.issubset(remove_repository_files_packages_instance.messages)
    assert pkghandler._get_packages_to_remove.called == 1
    assert pkghandler.remove_pkgs_unless_from_redhat.called == 1
    assert pkghandler._get_packages_to_remove.command == system_info.repofile_pkgs
    assert remove_repository_files_packages_instance.result.level == actions.STATUS_CODE["SUCCESS"]


def test_remove_repository_files_packages_dependency_order(remove_repository_files_packages_instance):
    expected_dependencies = ("BACKUP_REDHAT_RELEASE",)

    assert expected_dependencies == remove_repository_files_packages_instance.dependencies


def test_remove_repository_files_packages_error(remove_repository_files_packages_instance, monkeypatch):
    monkeypatch.setattr(system_info, "repofile_pkgs", [])
    monkeypatch.setattr(
        pkghandler, "remove_pkgs_unless_from_redhat", mock.Mock(side_effect=SystemExit("Raising SystemExit"))
    )

    remove_repository_files_packages_instance.run()

    unit_tests.assert_actions_result(
        remove_repository_files_packages_instance,
        level="ERROR",
        id="REPOSITORY_FILE_PACKAGE_REMOVAL_FAILED",
        message="Raising SystemExit",
    )
