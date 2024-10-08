# -*- coding: utf-8 -*-
#
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

from convert2rhel import actions, pkgmanager
from convert2rhel.actions.system_checks import package_updates
from convert2rhel.unit_tests.conftest import centos8, oracle8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def package_updates_action():
    return package_updates.PackageUpdates()


@oracle8
def test_check_package_updates_skip_on_not_latest_ol(pretend_os, caplog, package_updates_action, monkeypatch):
    monkeypatch.setattr(package_updates.system_info, "eus_system", value=True)

    diagnosis = "Did not perform the check because there were no publicly available Oracle Linux Server 8.6 repositories available."
    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="PACKAGE_UPDATES_CHECK_SKIP_NO_PUBLIC_REPOSITORIES",
                title="Did not perform the package updates check",
                description="Please refer to the diagnosis for further information",
                diagnosis=diagnosis,
                remediations=None,
                variables={},
            ),
        )
    )
    package_updates_action.run()

    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)
    assert diagnosis in caplog.records[-1].message
    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)


@centos8
def test_check_package_updates(pretend_os, monkeypatch, caplog, package_updates_action):
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=lambda: [])

    package_updates_action.run()
    assert "System is up-to-date." in caplog.records[-1].message


@centos8
def test_check_package_updates_not_up_to_date(pretend_os, monkeypatch, package_updates_action, caplog):
    packages = ["package-2", "package-1"]
    diagnosis = (
        "The system has 2 package(s) not updated based on repositories defined in the system repositories.\n"
        "List of packages to update: package-1 package-2.\n\n"
        "Not updating the packages may cause the conversion to fail.\n"
        "Consider updating the packages before proceeding with the conversion."
    )
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=lambda: packages)

    package_updates_action.run()
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="OUT_OF_DATE_PACKAGES",
                title="Outdated packages detected",
                description="Please refer to the diagnosis for further information",
                diagnosis=diagnosis,
                remediations="Run yum update to update all the packages on the system.",
                variables={},
            ),
        )
    )

    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)


@centos8
def test_check_package_updates_with_repoerror_warning(pretend_os, monkeypatch, caplog, package_updates_action):
    get_total_packages_to_update_mock = mock.Mock(side_effect=pkgmanager.RepoError("This is an error"))
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=get_total_packages_to_update_mock)

    diagnosis = (
        "There was an error while checking whether the installed packages are up-to-date. Having an updated system is"
        " an important prerequisite for a successful conversion. Consider verifying the system is up to date manually"
        " before proceeding with the conversion. This is an error"
    )
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="PACKAGE_UP_TO_DATE_CHECK_MESSAGE",
                title="Package up to date check fail",
                description="Please refer to the diagnosis for further information",
                diagnosis=diagnosis,
                remediations=None,
                variables={},
            ),
        )
    )
    package_updates_action.run()

    assert diagnosis in caplog.records[-1].message
    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)
