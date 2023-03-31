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
import unittest

import pytest
import six

from convert2rhel import actions, backup, redhatrelease, repo, unit_tests
from convert2rhel.actions.pre_ponr_changes import backup_system
from convert2rhel.backup import RestorableFile
from convert2rhel.redhatrelease import OS_RELEASE_FILEPATH


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def backup_redhat_release_action():
    return backup_system.BackupRedhatRelease()


@pytest.fixture
def backup_repository_action():
    return backup_system.BackupRepository()


class RestorableFileMock(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0

    def __call__(self, filepath):
        self.filepath = filepath
        return self

    def backup(self):
        self.called += 1


class TestBackupSystem:
    def test_backup_redhat_release_calls(self, backup_redhat_release_action, monkeypatch):
        monkeypatch.setattr(backup, "RestorableFile", RestorableFileMock())
        backup_redhat_release_action.run()
        assert backup_system.backup.RestorableFile.called == 2

    def test_backup_repository_calls(self, backup_repository_action, monkeypatch):
        backup_varsdir_mock = mock.Mock()
        backup_yum_repos_mock = mock.Mock()

        monkeypatch.setattr(repo, "backup_yum_repos", backup_yum_repos_mock)
        monkeypatch.setattr(repo, "backup_varsdir", backup_varsdir_mock)

        backup_repository_action.run()

        backup_yum_repos_mock.assert_called_once()
        backup_varsdir_mock.assert_called_once()

    @pytest.mark.parametrize(
        ("is_file", "exception"),
        ((False, True),),
    )
    def test_backup_redhat_release_error(self, backup_redhat_release_action, is_file, exception, monkeypatch):
        is_file_mock = mock.MagicMock(return_value=is_file)
        monkeypatch.setattr(os.path, "isfile", value=is_file_mock)

        if exception:
            backup_redhat_release_action.run()
            unit_tests.assert_actions_result(
                backup_redhat_release_action,
                status="ERROR",
                error_id="UNKNOWN_ERROR",
                message="Error: Unable to find the /etc/system-release file containing the OS name and version",
            )
