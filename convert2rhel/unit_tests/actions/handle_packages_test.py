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

from convert2rhel import actions, pkghandler, unit_tests, utils
from convert2rhel.actions.pre_ponr_changes import handle_packages
from convert2rhel.systeminfo import system_info


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class PrintPkgInfoMocked(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0
        self.pkgs = []

    def __call__(self, pkgs):
        self.called += 1
        self.pkgs = pkgs


@pytest.fixture
def list_third_party_packages_instance():
    return handle_packages.ListThirdPartyPackages()


def test_list_third_party_packages_no_packages(list_third_party_packages_instance, monkeypatch, caplog):
    monkeypatch.setattr(pkghandler, "get_third_party_pkgs", lambda: [])

    list_third_party_packages_instance.run()

    assert "No third party packages installed" in caplog.records[-1].message
    assert list_third_party_packages_instance.status == actions.STATUS_CODE["SUCCESS"]


def test_list_third_party_packages(list_third_party_packages_instance, monkeypatch, caplog):
    monkeypatch.setattr(pkghandler, "get_third_party_pkgs", unit_tests.GetInstalledPkgsWFingerprintsMocked())
    monkeypatch.setattr(pkghandler, "print_pkg_info", PrintPkgInfoMocked())
    monkeypatch.setattr(utils, "ask_to_continue", unit_tests.DumbCallableObject())

    list_third_party_packages_instance.run()

    assert len(pkghandler.print_pkg_info.pkgs) == 3
    assert "Only packages signed by" in caplog.records[-1].message

    assert list_third_party_packages_instance.status == actions.STATUS_CODE["SUCCESS"]


class CommandCallableObject(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0
        self.command = None

    def __call__(self, command):
        self.called += 1
        self.command = command
        return


@pytest.fixture
def remove_excluded_packages_instance():
    return handle_packages.RemoveExcludedPackages()


def test_remove_excluded_packages(remove_excluded_packages_instance, monkeypatch):
    excluded_pkgs = ["installed_pkg", "not_installed_pkg"]
    monkeypatch.setattr(system_info, "excluded_pkgs", excluded_pkgs)
    monkeypatch.setattr(pkghandler, "remove_pkgs_with_confirm", CommandCallableObject())

    remove_excluded_packages_instance.run()

    assert pkghandler.remove_pkgs_with_confirm.called == 1
    assert pkghandler.remove_pkgs_with_confirm.command == excluded_pkgs
    assert remove_excluded_packages_instance.status == actions.STATUS_CODE["SUCCESS"]


def test_remove_excluded_packages_error(remove_excluded_packages_instance, monkeypatch):
    monkeypatch.setattr(system_info, "excluded_pkgs", [])
    monkeypatch.setattr(pkghandler, "remove_pkgs_with_confirm", mock.Mock(side_effect=SystemExit("Raising SystemExit")))

    remove_excluded_packages_instance.run()

    unit_tests.assert_actions_result(
        remove_excluded_packages_instance,
        status="ERROR",
        error_id="PACKAGE_REMOVAL_FAILED",
        message="Raising SystemExit",
    )


@pytest.fixture
def remove_repository_files_packages_instance():
    return handle_packages.RemoveRepositoryFilesPackages()


def test_remove_repository_files_packages(remove_repository_files_packages_instance, monkeypatch):
    repofile_pkgs = ["installed_pkg", "not_installed_pkg"]
    monkeypatch.setattr(system_info, "repofile_pkgs", repofile_pkgs)
    monkeypatch.setattr(pkghandler, "remove_pkgs_with_confirm", CommandCallableObject())

    remove_repository_files_packages_instance.run()

    assert pkghandler.remove_pkgs_with_confirm.called == 1
    assert pkghandler.remove_pkgs_with_confirm.command == repofile_pkgs
    assert remove_repository_files_packages_instance.status == actions.STATUS_CODE["SUCCESS"]


def test_remove_repository_files_packages_error(remove_repository_files_packages_instance, monkeypatch):
    monkeypatch.setattr(system_info, "repofile_pkgs", [])
    monkeypatch.setattr(pkghandler, "remove_pkgs_with_confirm", mock.Mock(side_effect=SystemExit("Raising SystemExit")))

    remove_repository_files_packages_instance.run()

    unit_tests.assert_actions_result(
        remove_repository_files_packages_instance,
        status="ERROR",
        error_id="PACKAGE_REMOVAL_FAILED",
        message="Raising SystemExit",
    )
