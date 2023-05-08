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

from convert2rhel import repo, unit_tests
from convert2rhel.actions.pre_ponr_changes import backup_system


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


class RestorableFileExceptionMock(RestorableFileMock):
    def backup(self):
        raise SystemExit("File not found")


class TestBackupSystem:
    def test_backup_redhat_release_calls(self, backup_redhat_release_action, monkeypatch):
        monkeypatch.setattr(backup_system, "system_release_file", RestorableFileMock())
        monkeypatch.setattr(backup_system, "os_release_file", RestorableFileMock())

        backup_redhat_release_action.run()

        assert backup_system.system_release_file.called == 1
        assert backup_system.os_release_file.called == 1

    def test_backup_repository_calls(self, backup_repository_action, monkeypatch):
        backup_varsdir_mock = mock.Mock()
        backup_yum_repos_mock = mock.Mock()

        monkeypatch.setattr(repo, "backup_yum_repos", backup_yum_repos_mock)
        monkeypatch.setattr(repo, "backup_varsdir", backup_varsdir_mock)

        backup_repository_action.run()

        backup_yum_repos_mock.assert_called_once()
        backup_varsdir_mock.assert_called_once()

    def test_backup_redhat_release_error_system_release_file(self, backup_redhat_release_action, monkeypatch):
        monkeypatch.setattr(backup_system, "system_release_file", RestorableFileExceptionMock())

        backup_redhat_release_action.run()
        unit_tests.assert_actions_result(
            backup_redhat_release_action, status="ERROR", error_id="UNKNOWN_ERROR", message="File not found"
        )

    def test_backup_redhat_release_error_os_release_file(self, backup_redhat_release_action, monkeypatch):
        monkeypatch.setattr(backup_system, "system_release_file", mock.Mock())
        monkeypatch.setattr(backup_system, "os_release_file", RestorableFileExceptionMock())

        backup_redhat_release_action.run()
        unit_tests.assert_actions_result(
            backup_redhat_release_action, status="ERROR", error_id="UNKNOWN_ERROR", message="File not found"
        )
