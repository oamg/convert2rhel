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

from collections import namedtuple

import pytest
import six

from convert2rhel import actions, pkgmanager, unit_tests
from convert2rhel.actions import package_updates
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
        "Skipping the check because there are no publicly available Oracle Linux Server 8.4 repositories available."
    )

    package_updates_action.run()

    assert message in caplog.records[-1].message


@pytest.mark.parametrize(
    ("packages", "exception", "expected"),
    (
        (["package-1", "package-2"], True, "The system has {0} package(s) not updated"),
        ([], False, "System is up-to-date."),
    ),
)
@centos8
def test_check_package_updates(pretend_os, packages, exception, expected, monkeypatch, caplog, package_updates_action):
    monkeypatch.setattr(actions.package_updates, "get_total_packages_to_update", value=lambda reposdir: packages)
    monkeypatch.setattr(actions.package_updates, "ask_to_continue", value=lambda: mock.Mock())

    package_updates_action.run()
    if exception:
        expected = expected.format(len(packages))

    assert expected in caplog.records[-1].message


def test_check_package_updates_with_repoerror(monkeypatch, caplog, package_updates_action):
    get_total_packages_to_update_mock = mock.Mock(side_effect=pkgmanager.RepoError)
    monkeypatch.setattr(
        actions.package_updates, "get_total_packages_to_update", value=get_total_packages_to_update_mock
    )
    monkeypatch.setattr(actions.package_updates, "ask_to_continue", value=lambda: mock.Mock())

    package_updates_action.run()
    # This is -2 because the last message is the error from the RepoError class.
    assert (
        "There was an error while checking whether the installed packages are up-to-date." in caplog.records[-2].message
    )


@centos8
def test_check_package_updates_without_internet(pretend_os, tmpdir, monkeypatch, caplog, package_updates_action):
    monkeypatch.setattr(actions.package_updates, "get_hardcoded_repofiles_dir", value=lambda: str(tmpdir))
    system_info.has_internet_access = False
    package_updates_action.run()

    assert "Skipping the check as no internet connection has been detected." in caplog.records[-1].message
