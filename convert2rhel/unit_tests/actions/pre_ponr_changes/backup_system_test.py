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


import hashlib
import os

import pytest
import six

from convert2rhel import subscription, unit_tests
from convert2rhel.actions.pre_ponr_changes import backup_system
from convert2rhel.backup import files
from convert2rhel.backup.files import RestorableFile
from convert2rhel.toolopts import PRE_RPM_VA_LOG_FILENAME
from convert2rhel.unit_tests import CriticalErrorCallableObject
from convert2rhel.unit_tests.conftest import all_systems, centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def backup_redhat_release_action():
    return backup_system.BackupRedhatRelease()


@pytest.fixture
def backup_repository_action():
    return backup_system.BackupRepository()


@pytest.fixture
def backup_variables_action():
    return backup_system.BackupYumVariables()


class RestorableFileBackupMocked(CriticalErrorCallableObject):
    method_spec = RestorableFile.enable


@pytest.fixture
def backup_package_files_action():
    return backup_system.BackupPackageFiles()


@pytest.fixture
def generate_vars(tmpdir):
    """Create yum and dnf vars folders with file for backup."""
    tmpdir = tmpdir.mkdir("etc")

    yum_vars = tmpdir.mkdir("yum").mkdir("vars").join("yum_test_var")
    dnf_vars = tmpdir.mkdir("dnf").mkdir("vars").join("dnf_test_var")
    yum_vars.write("yum_test_var")
    dnf_vars.write("dnf_test_var")

    return str(dnf_vars), str(yum_vars)


def generate_repo(tmpdir, name):
    """Create .repo file for backup."""
    yum_repofile = tmpdir.mkdir("etc").mkdir("yum.repos.d").join(name)
    yum_repofile.write(name)

    return str(yum_repofile)


class TestBackupSystem:
    def test_backup_redhat_release_calls(self, backup_redhat_release_action, monkeypatch):
        monkeypatch.setattr(
            backup_system, "system_release_file", mock.create_autospec(backup_system.system_release_file)
        )
        monkeypatch.setattr(backup_system, "os_release_file", mock.create_autospec(backup_system.os_release_file))

        backup_redhat_release_action.run()

        assert backup_system.system_release_file.enable.call_count == 1
        assert backup_system.os_release_file.enable.call_count == 1

    def test_backup_redhat_release_error_system_release_file(self, backup_redhat_release_action, monkeypatch):
        mock_sys_release_file = RestorableFileBackupMocked(
            id_="FAILED_TO_SAVE_FILE_TO_BACKUP_DIR",
            title="Failed to copy file to the backup directory.",
            description="Failure while backing up a file.",
            diagnosis="Failed to backup /etc/system-release. Errno: 2, Error: File not found",
        )
        monkeypatch.setattr(backup_system.system_release_file, "enable", mock_sys_release_file)

        backup_redhat_release_action.run()

        unit_tests.assert_actions_result(
            backup_redhat_release_action,
            level="ERROR",
            id="FAILED_TO_SAVE_FILE_TO_BACKUP_DIR",
            title="Failed to copy file to the backup directory.",
            description="Failure while backing up a file.",
            diagnosis="Failed to backup /etc/system-release. Errno: 2, Error: File not found",
        )

    def test_backup_redhat_release_error_os_release_file(self, backup_redhat_release_action, monkeypatch):
        mock_sys_release_file = mock.create_autospec(backup_system.system_release_file.enable)
        mock_os_release_file = RestorableFileBackupMocked(
            id_="FAILED_TO_SAVE_FILE_TO_BACKUP_DIR",
            title="Failed to copy file to the backup directory.",
            description="Failure while backing up a file.",
            diagnosis="Failed to backup /etc/os-release. Errno: 2, Error: File not found",
        )

        monkeypatch.setattr(backup_system.system_release_file, "enable", mock_sys_release_file)
        monkeypatch.setattr(backup_system.os_release_file, "enable", mock_os_release_file)

        backup_redhat_release_action.run()

        unit_tests.assert_actions_result(
            backup_redhat_release_action,
            level="ERROR",
            id="FAILED_TO_SAVE_FILE_TO_BACKUP_DIR",
            title="Failed to copy file to the backup directory.",
            description="Failure while backing up a file.",
            diagnosis="Failed to backup /etc/os-release. Errno: 2, Error: File not found",
        )

    @pytest.mark.parametrize(
        ("rpm_va_output", "expected", "message"),
        (
            (
                """     missing   d /usr/share/info/ed.info.gz
                S.5.?..T. c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                S.5.?..T.        /etc/yum.repos.d/CentOS-Linux-AppStream.repo


                .......T.  c /etc/yum.repos.d/CentOS-Linux-Debuginfo.repo
                SM.DLUGTP  c /etc/yum.repos.d/CentOS-Linux-Plus.repo

                """,
                [
                    {"status": "missing", "file_type": "d", "path": "/usr/share/info/ed.info.gz"},
                    {
                        "status": "S5T",
                        "file_type": "c",
                        "path": "/etc/yum.repos.d/CentOS-Linux-AppStream.repo",
                    },
                    {
                        "status": "S5T",
                        "file_type": None,
                        "path": "/etc/yum.repos.d/CentOS-Linux-AppStream.repo",
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
                None,
            ),
            (
                "S.5.?..5.      /etc/yum.repos.d/CentOS-Linux-AppStream.repo",
                [],
                "Skipping invalid output S.5.?..5.      /etc/yum.repos.d/CentOS-Linux-AppStream.repo",
            ),
            (
                "               ",
                [],
                None,
            ),
            (
                "SM5DLUGTP   cd   /etc/yum.repos.d/CentOS-Linux-AppStream.repo",
                [],
                "Skipping invalid output SM5DLUGTP   cd   /etc/yum.repos.d/CentOS-Linux-AppStream.repo",
            ),
            (
                """c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo
                S.5.?..T. c
                """,
                [],
                "Skipping invalid output c     /etc/yum.repos.d/CentOS-Linux-AppStream.repo",
            ),
            (
                """
                S.5.?..T. c
                """,
                [],
                "Skipping invalid output S.5.?..T. c",
            ),
        ),
    )
    def test_get_changed_package_files(self, rpm_va_output, expected, message, caplog, tmpdir, monkeypatch):
        rpm_va_logfile_path = os.path.join(str(tmpdir), PRE_RPM_VA_LOG_FILENAME)

        monkeypatch.setattr(backup_system, "LOG_DIR", str(tmpdir))
        with open(rpm_va_logfile_path, "w") as f:
            f.write(rpm_va_output)

        backup_package_file = backup_system.BackupPackageFiles()
        output = backup_package_file._get_changed_package_files()

        assert output == expected
        if message:
            assert message in caplog.text
        else:
            assert "" == caplog.text

    @pytest.mark.parametrize(
        ("env_var", "message"),
        (
            (True, "Skipping backup of the package files. CONVERT2RHEL_INCOMPLETE_ROLLBACK detected."),
            (False, "Missing file {rpm_va_output} in it's location"),
        ),
    )
    def test_get_changed_package_files_missing(self, caplog, message, env_var, tmpdir, monkeypatch):
        monkeypatch.setattr(backup_system, "LOG_DIR", str(tmpdir))

        if env_var:
            os.environ["CONVERT2RHEL_INCOMPLETE_ROLLBACK"] = "1"
        else:
            # Unset the variable
            os.environ.pop("CONVERT2RHEL_INCOMPLETE_ROLLBACK", None)

        backup_package_file = backup_system.BackupPackageFiles()

        try:
            backup_package_file._get_changed_package_files()
        except SystemExit:
            path = os.path.join(str(tmpdir), PRE_RPM_VA_LOG_FILENAME)
            assert caplog.records[-1].message == message.format(rpm_va_output=path)
        else:
            assert caplog.records[-1].message == message

    @pytest.mark.parametrize(
        ("rpm_va_output", "message"),
        (
            ("S.5.?..T.     c   /etc/os-release", "File {filepath} already backed up - not backing up again"),
            ("S.5.?..T.     c   /etc/yum/vars/filename_4", "File {filepath} already backed up - not backing up again"),
        ),
    )
    def test_backup_package_file_run(
        self, rpm_va_output, message, tmpdir, monkeypatch, caplog, backup_package_files_action
    ):
        # Prepare the output of rpm -va and save it to destination
        rpm_va_logfile_path = os.path.join(str(tmpdir), PRE_RPM_VA_LOG_FILENAME)
        with open(rpm_va_logfile_path, "w") as f:
            f.write(rpm_va_output)

        monkeypatch.setattr(backup_system, "LOG_DIR", str(tmpdir))

        backup_package_files_action.run()

        message = message.format(filepath=rpm_va_output.split()[-1])

        assert message == caplog.records[-1].message

    @pytest.mark.parametrize(
        ("rpm_va_output_lines", "backed_up"),
        (
            (
                [
                    "missing       d   {path}/filename_0",
                    "S.5.?..T.     c   {path}/filename_1",
                    "S.5.?..T.         /invalid/path/filename_2",
                    ".......T.     c   {path}/filename_3",
                    "S.5.?..T.     c   {path}/filename_4",
                ],
                (False, True, False, False, True),
            ),
        ),
    )
    def test_backup_package_file_complete(
        self,
        rpm_va_output_lines,
        backed_up,
        tmpdir,
        monkeypatch,
        backup_package_files_action,
        global_backup_control,
    ):
        # Prepare the rpm -va ouput to the PRE_RPM_VA_LOG_FILENAME file
        rpm_va_output = ""
        rpm_va_path = str(tmpdir)
        for i, line in enumerate(rpm_va_output_lines):
            status = line.split()[0]
            # Need to insert tmpdir into the filepath
            rpm_va_output_lines[i] = rpm_va_output_lines[i].format(path=rpm_va_path)
            # Write some content to the newly created path if the file is present on the system
            if status != "missing":
                try:
                    with open(rpm_va_output_lines[i].split()[-1], mode="w") as f:
                        # Append the original path to the content
                        f.write("Content for testing of file %s" % rpm_va_output_lines[i].split()[-1])
                except (OSError, IOError):
                    # case with invalid filepath
                    pass
            # Prepared rpm -Va output with paths to tmpdir
            rpm_va_output += rpm_va_output_lines[i] + "\n"
        # Write the data to a file since data from systeminfo are being used
        rpm_va_logfile_path = os.path.join(rpm_va_path, PRE_RPM_VA_LOG_FILENAME)
        with open(rpm_va_logfile_path, "w") as f:
            f.write(rpm_va_output)

        backup_dir = str(tmpdir.mkdir("backup"))

        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)
        monkeypatch.setattr(backup_system, "LOG_DIR", rpm_va_path)

        backup_package_files_action.run()

        # Change the original files (remove, create)
        for i, line in enumerate(rpm_va_output_lines):
            original_file_path = line.split()[-1]
            status = line.split()[0]

            # Get the filename from the original path
            filename = os.path.basename(original_file_path)
            dirname = os.path.dirname(original_file_path)
            hashed_directory = os.path.join(backup_dir, hashlib.md5(dirname.encode()).hexdigest())
            backed_up_file_path = os.path.join(hashed_directory, filename)

            if backed_up[i]:
                # Check if the file exists and contains right content
                with open(backed_up_file_path, mode="r") as f:
                    assert f.read() == "Content for testing of file %s" % original_file_path
                os.remove(original_file_path)
            elif status == "missing":
                with open(original_file_path, mode="w") as f:
                    # Append the original path to the content
                    f.write("Content for testing of file %s" % original_file_path)
            else:
                assert not os.path.isfile(backed_up_file_path)

        global_backup_control.pop_all()

        # Check the existence/nonexistence and content rolled back file
        for i, line in enumerate(rpm_va_output_lines):
            original_file_path = line.split()[-1]
            status = line.split()[0]
            if backed_up[i]:
                assert os.path.isfile(original_file_path)
                with open(original_file_path, mode="r") as f:
                    assert f.read() == "Content for testing of file %s" % original_file_path
            elif status == "missing":
                assert not os.path.isfile(original_file_path)


class TestBackupRepository:
    def test_backup_repository_complete(self, monkeypatch, tmpdir, backup_repository_action, global_backup_control):
        """Test backup, remove the originals and restore them from backup."""
        yum_repo = generate_repo(tmpdir, name="test.repo")

        backup_dir = str(tmpdir.mkdir("backup"))

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_REPOFILE_DIR", os.path.dirname(yum_repo))
        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)

        backup_repository = backup_repository_action

        backup_repository.run()

        # Remove the original files
        os.remove(yum_repo)
        assert not os.path.isfile(yum_repo)

        global_backup_control.pop_all()

        # Check presence of restored files
        assert os.path.isfile(yum_repo)
        with open(yum_repo, mode="r") as f:
            assert f.read() == os.path.basename(yum_repo)

    def test_backup_repository_redhat(self, monkeypatch, tmpdir, backup_repository_action, caplog):
        """Test if redhat.repo is not backed up."""
        redhat_repo = generate_repo(tmpdir, "redhat.repo")

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_REPOFILE_DIR", os.path.dirname(redhat_repo))
        monkeypatch.setattr(subscription, "should_subscribe", mock.Mock(side_effect=lambda: False))
        backup_repository = backup_repository_action
        backup_repository.run()

        assert "Skipping backup of redhat.repo as it is not needed." == caplog.records[-1].message

    def test_backup_repository_other_files(self, monkeypatch, tmpdir, backup_repository_action, caplog):
        """Test if redhat.repo is not backed up."""
        non_repo_file = generate_repo(tmpdir, "redhat.nonrepo")

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_REPOFILE_DIR", os.path.dirname(non_repo_file))
        backup_repository = backup_repository_action
        backup_repository.run()
        assert "Skipping backup as file is not a repository file." == caplog.records[-1].message

    def test_backup_repository_no_repofile_presence(self, tmpdir, monkeypatch, caplog, backup_repository_action):
        """Test empty path, nothing for backup."""
        etc = tmpdir.mkdir("etc")

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_REPOFILE_DIR", str(etc))

        backup_repository = backup_repository_action

        backup_repository.run()
        assert ("Repository folder %s seems to be empty." % etc) in caplog.text


class TestBackupVariables:
    @all_systems
    def test_backup_variables_nonexisting_path(self, tmpdir, monkeypatch, caplog, backup_variables_action, pretend_os):
        """Test empty paths, nothing for backup."""
        etc = tmpdir.mkdir("etc")

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_VARS_DIR", str(etc))
        monkeypatch.setattr(backup_system, "DEFAULT_DNF_VARS_DIR", str(etc))

        backup_variables = backup_variables_action

        backup_variables.run()

        assert "No variables files backed up." in caplog.text

    @centos7
    def test_backup_variables_only_yum(self, pretend_os, monkeypatch, tmpdir, generate_vars, backup_variables_action):
        """Test when DNF is not present - DNF vars dir is not backed up."""
        dnf_vars, yum_vars = generate_vars

        backup_dir = str(tmpdir.mkdir("backup"))

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_VARS_DIR", os.path.dirname(yum_vars))
        monkeypatch.setattr(backup_system, "DEFAULT_DNF_VARS_DIR", os.path.dirname(dnf_vars))
        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)

        backup_variables = backup_variables_action

        backup_variables.run()

        # Mapping if the file should be backed up or not
        orig_path_dict = {dnf_vars: False, yum_vars: True}

        # Get the target path of backed up file and check presence of the file
        for path, value in orig_path_dict.items():
            filename = os.path.basename(path)
            dirname = os.path.dirname(path)
            hashed_directory = os.path.join(backup_dir, hashlib.md5(dirname.encode()).hexdigest())
            backed_up_path = os.path.join(hashed_directory, filename)

            assert os.path.exists(backed_up_path) == value

    @centos8
    def test_backup_variables_complete(
        self, monkeypatch, tmpdir, generate_vars, backup_variables_action, global_backup_control, pretend_os
    ):
        """Test backup, remove the originals and restore them from backup."""
        dnf_vars, yum_vars = generate_vars

        backup_dir = str(tmpdir.mkdir("backup"))

        monkeypatch.setattr(backup_system, "DEFAULT_YUM_VARS_DIR", os.path.dirname(yum_vars))
        monkeypatch.setattr(backup_system, "DEFAULT_DNF_VARS_DIR", os.path.dirname(dnf_vars))
        monkeypatch.setattr(files, "BACKUP_DIR", backup_dir)

        backup_variables = backup_variables_action

        backup_variables.run()

        orig_path_list = [dnf_vars, yum_vars]

        # Remove the original files
        for path in orig_path_list:
            os.remove(path)
            assert not os.path.isfile(path)

        global_backup_control.pop_all()

        # Check presence of restored files
        for path in orig_path_list:
            assert os.path.isfile(path)
            with open(path, mode="r") as f:
                assert f.read() == os.path.basename(path)
