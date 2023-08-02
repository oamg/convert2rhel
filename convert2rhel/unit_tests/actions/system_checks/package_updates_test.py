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

import os

import pytest
import six

from convert2rhel import actions, pkgmanager, unit_tests
from convert2rhel.actions.system_checks import package_updates
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests.conftest import centos8, oracle8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def package_updates_action():
    return package_updates.PackageUpdates()


@oracle8
def test_check_package_updates_skip_on_not_latest_ol(pretend_os, caplog, package_updates_action):
    message = (
        "Skipping the check because there are no publicly available Oracle Linux Server 8.6 repositories available."
    )
    expected = set(
        (
            actions.ActionMessage(
                level="INFO",
                id="PACKAGE_UPDATES_CHECK_SKIP_NO_PUBLIC_REPOSITORIES",
                message=(
                    "Skipping the check because there are no publicly available Oracle Linux Server 8.6 repositories available."
                ),
            ),
        )
    )

    package_updates_action.run()

    assert message in caplog.records[-1].message
    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)


@pytest.mark.parametrize(
    ("packages", "exception", "expected"),
    (
        (["package-1", "package-2"], True, "The system has {0} package(s) not updated"),
        ([], False, "System is up-to-date."),
    ),
)
@centos8
def test_check_package_updates(pretend_os, packages, exception, expected, monkeypatch, caplog, package_updates_action):
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=lambda reposdir: packages)

    package_updates_action.run()
    if exception:
        expected = expected.format(len(packages))

    assert expected in caplog.records[-1].message


@centos8
def test_check_package_updates_not_up_to_date(pretend_os, monkeypatch, package_updates_action, caplog):
    packages = ["package-1", "package-2"]
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=lambda reposdir: packages)
    package_updates_action.run()
    unit_tests.assert_actions_result(
        package_updates_action,
        level="OVERRIDABLE",
        id="OUT_OF_DATE_PACKAGES",
        message=(
            "The system has 2 package(s) not updated based on the enabled system repositories.\n"
            "List of packages to update: package-1 package-2.\n\n"
            "Not updating the packages may cause the conversion to fail.\n"
            "Consider updating the packages before proceeding with the conversion."
        ),
    )
    assert (
        "The system has 2 package(s) not updated based on the enabled system repositories.\n"
        in caplog.records[-1].message
    )


@centos8
def test_check_package_updates_not_up_to_date_skip(pretend_os, monkeypatch, package_updates_action, caplog):
    packages = ["package-1", "package-2"]
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=lambda reposdir: packages)
    monkeypatch.setattr(
        os,
        "environ",
        {"CONVERT2RHEL_PACKAGE_NOT_UP_TO_DATE_SKIP": 1},
    )
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="PACKAGE_NOT_UP_TO_DATE_MESSAGE",
                message=(
                    "The system has 2 package(s) not updated based on the enabled system repositories.\n"
                    "List of packages to update: package-1 package-2.\n\n"
                    "Not updating the packages may cause the conversion to fail.\n"
                    "Consider updating the packages before proceeding with the conversion."
                ),
            ),
            actions.ActionMessage(
                level="WARNING",
                id="SKIP_PACKAGE_NOT_UP_TO_DATE",
                message=(
                    "Detected 'CONVERT2RHEL_PACKAGE_NOT_UP_TO_DATE_SKIP' environment variable, we will skip "
                    "the package up-to-date check.\n"
                    "Beware, this could leave your system in a broken state."
                ),
            ),
        )
    )

    package_updates_action.run()
    assert (
        "The system has 2 package(s) not updated based on the enabled system repositories.\n"
        in caplog.records[-1].message
    )
    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)


def test_check_package_updates_with_repoerror(monkeypatch, caplog, package_updates_action):
    get_total_packages_to_update_mock = mock.Mock(side_effect=pkgmanager.RepoError("This is an error"))
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=get_total_packages_to_update_mock)
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=get_total_packages_to_update_mock)
    package_updates_action.run()
    unit_tests.assert_actions_result(
        package_updates_action,
        level="OVERRIDABLE",
        id="PACKAGE_UP_TO_DATE_CHECK_FAIL",
        message=(
            "There was an error while checking whether the installed packages are up-to-date. Having an updated system is"
            " an important prerequisite for a successful conversion. Consider verifyng the system is up to date manually"
            " before proceeding with the conversion. This is an error"
        ),
    )

    assert (
        "There was an error while checking whether the installed packages are up-to-date." in caplog.records[-1].message
    )


def test_check_package_updates_with_repoerror_skip(monkeypatch, caplog, package_updates_action):
    get_total_packages_to_update_mock = mock.Mock(side_effect=pkgmanager.RepoError("This is an error"))
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=get_total_packages_to_update_mock)
    monkeypatch.setattr(package_updates, "get_total_packages_to_update", value=get_total_packages_to_update_mock)
    monkeypatch.setattr(
        os,
        "environ",
        {"CONVERT2RHEL_PACKAGE_UP_TO_DATE_CHECK_SKIP": 1},
    )
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="PACKAGE_UP_TO_DATE_CHECK_MESSAGE",
                message=(
                    "There was an error while checking whether the installed packages are up-to-date. Having an updated system is"
                    " an important prerequisite for a successful conversion. Consider verifyng the system is up to date manually"
                    " before proceeding with the conversion. This is an error"
                ),
            ),
            actions.ActionMessage(
                level="WARNING",
                id="SKIP_PACKAGE_UP_TO_DATE_CHECK",
                message=(
                    "Detected 'CONVERT2RHEL_PACKAGE_UP_TO_DATE_CHECK_SKIP' environment variable, we will skip "
                    "the package up-to-date check.\n"
                    "Beware, this could leave your system in a broken state."
                ),
            ),
        )
    )

    package_updates_action.run()

    assert (
        "There was an error while checking whether the installed packages are up-to-date." in caplog.records[-1].message
    )
    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)


@centos8
def test_check_package_updates_without_internet(pretend_os, tmpdir, monkeypatch, caplog, package_updates_action):
    monkeypatch.setattr(package_updates, "get_hardcoded_repofiles_dir", value=lambda: str(tmpdir))
    system_info.has_internet_access = False
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="PACKAGE_UPDATES_CHECK_SKIP_NO_INTERNET",
                message="Skipping the check as no internet connection has been detected.",
            ),
        )
    )
    package_updates_action.run()

    assert "Skipping the check as no internet connection has been detected." in caplog.records[-1].message
    assert expected.issuperset(package_updates_action.messages)
    assert expected.issubset(package_updates_action.messages)
