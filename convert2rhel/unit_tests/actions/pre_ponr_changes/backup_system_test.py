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

from convert2rhel import backup, repo, unit_tests, utils
from convert2rhel.actions.pre_ponr_changes import backup_system


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def backup_redhat_release_action():
    return backup_system.BackupRedhatRelease()


@pytest.fixture
def backup_repository_action():
    return backup_system.BackupRepository()


@pytest.fixture
def backup_package_files_action():
    return backup_system.BackupPackageFiles()


class RestorableFileMock(unit_tests.MockFunction):
    def __init__(self, filepath=None):
        self.filepath = filepath
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
            backup_redhat_release_action,
            level="ERROR",
            id="UNKNOWN_ERROR",
            title="An unknown error has occurred",
            description="File not found",
        )

    def test_backup_redhat_release_error_os_release_file(self, backup_redhat_release_action, monkeypatch):
        monkeypatch.setattr(backup_system, "system_release_file", mock.Mock())
        monkeypatch.setattr(backup_system, "os_release_file", RestorableFileExceptionMock())

        backup_redhat_release_action.run()
        unit_tests.assert_actions_result(
            backup_redhat_release_action,
            level="ERROR",
            id="UNKNOWN_ERROR",
            title="An unknown error has occurred",
            description="File not found",
        )

    @pytest.mark.parametrize(
        ("rpm_verify", "caplog_message", "output"),
        [
            (
                """     missing   d /usr/share/info/ed.info.gz
                S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                S.5.?..T.      /etc/yum.repos.d/CentOS-Linux-AppStream.repo

                S.5.?..5.      /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                .......T.  c /etc/yum.repos.d/CentOS-Linux-Debuginfo.repo
                SM.DLUGTP  c /etc/yum.repos.d/CentOS-Linux-Plus.repo
                """,
                "Skipping invalid output S.5.?..5.      /etc/yum.repos.d/CentOS-Linux-AppStream.repo",
                [
                    {"status": "missing", "file_type": "d", "path": "/usr/share/info/ed.info.gz"},
                    {
                        "status": "S5T",
                        "file_type": "c",
                        "path": "/etc/yum.repos.d/CentOS-Linux-AppStream.repo",
                        "backup": mock.ANY,
                    },
                    {
                        "status": "S5T",
                        "file_type": None,
                        "path": "/etc/yum.repos.d/CentOS-Linux-AppStream.repo",
                        "backup": mock.ANY,
                    },
                    {
                        "status": "T",
                        "file_type": "c",
                        "path": "/etc/yum.repos.d/CentOS-Linux-Debuginfo.repo",
                    },
                    {
                        "status": "SMDLUGTP",
                        "file_type": "c",
                        "path": "/etc/yum.repos.d/CentOS-Linux-Plus.repo",
                    },
                ],
            ),
            ("", None, []),
        ],
    )
    def test_backup_package_files_run(
        self, rpm_verify, caplog_message, output, caplog, backup_package_files_action, monkeypatch
    ):
        run_subprocess = mock.Mock(return_value=(rpm_verify, 0))

        monkeypatch.setattr(utils, "run_subprocess", run_subprocess)
        monkeypatch.setattr(backup, "RestorableFile", RestorableFileMock)

        backup_package_files_action.run()

        assert backup.package_files_changes == output
        if caplog_message:
            assert caplog_message in caplog.text

        for value in backup.package_files_changes:
            if value.get("backup"):
                assert isinstance(value.get("backup"), backup.RestorableFile)

    @pytest.mark.parametrize(
        ("data", "path_exists", "remove_call", "restore_call"),
        [
            (
                [
                    {
                        "status": "missing",
                        "file_type": "c",
                        "path": "anything",
                        "backup": mock.Mock(),
                    }
                ],
                True,
                1,
                0,
            ),
            (
                [
                    {
                        "status": "missing",
                        "file_type": "c",
                        "path": "anything",
                        "backup": mock.Mock(),
                    },
                    {
                        "status": "5",
                        "file_type": "c",
                        "path": "anything",
                        "backup": mock.Mock(),
                    },
                ],
                True,
                1,
                1,
            ),
            (
                [
                    {
                        "status": "missing",
                        "file_type": "c",
                        "path": "anything",
                        "backup": mock.Mock(),
                    }
                ],
                False,
                0,
                0,
            ),
        ],
    )
    def test_backup_package_files_rollback(self, data, path_exists, remove_call, restore_call, monkeypatch):
        exists = mock.Mock(return_value=path_exists)
        remove = mock.Mock()

        monkeypatch.setattr(os.path, "exists", exists)
        monkeypatch.setattr(os, "remove", remove)
        backup.package_files_changes = data

        backup_system.BackupPackageFiles.rollback_files()

        assert remove.call_count == remove_call

        restore_call_count = 0
        for file in data:
            restore_call_count += file["backup"].restore.call_count
        assert restore_call_count == restore_call
