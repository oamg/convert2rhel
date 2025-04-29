# Copyright(C) 2025 Red Hat, Inc.
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

# GitHub Copilot assisted in writing this file.

import pytest
import six

from convert2rhel import pkghandler
from convert2rhel.actions.pre_ponr_changes import yum_variables
from convert2rhel.backup.files import RestorableFile

six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    "pkg_names, owned_files, expected_files",
    [
        (["pkg1"], ["/etc/yum/vars/pkg1_var"], ["/etc/yum/vars/pkg1_var"]),
        (["pkg1"], ["/etc/yum/vars/pkg1_var", "/other_file"], ["/etc/yum/vars/pkg1_var"]),
        (
            ["pkg1", "pkg2"],
            ["/etc/yum/vars/pkg1_var", "/etc/yum/vars/pkg2_var"],
            ["/etc/yum/vars/pkg1_var", "/etc/yum/vars/pkg2_var"],
        ),
        (["pkg1"], [], []),
    ],
)
def test_get_yum_var_files_owned_by_pkgs(monkeypatch, pkg_names, owned_files, expected_files):
    action = yum_variables.BackUpYumVariables()

    def mock_get_files_owned_by_package(pkg):
        return [file for file in owned_files if "/{}_".format(pkg) in file]

    monkeypatch.setattr(
        "convert2rhel.actions.pre_ponr_changes.yum_variables.get_files_owned_by_package",
        mock_get_files_owned_by_package,
    )

    result = action._get_yum_var_files_owned_by_pkgs(pkg_names)

    assert set(result) == set(expected_files)


@pytest.mark.parametrize(
    "paths, expected_push_calls, log_message",
    [
        ([], 0, "No variable files to back up detected."),
        (
            ["/etc/yum/vars/pkg1_var", "/etc/yum/vars/pkg2_var"],
            2,
            "Yum variables successfully backed up.",
        ),
    ],
)
def test_back_up_var_files(
    monkeypatch, paths, expected_push_calls, log_message, global_system_info, global_backup_control, caplog
):
    action = yum_variables.BackUpYumVariables()
    global_system_info.name = "centos"
    monkeypatch.setattr(yum_variables, "system_info", global_system_info)
    monkeypatch.setattr(global_backup_control, "push", mock.Mock())

    action._back_up_var_files(paths)

    assert caplog.records[0].levelname == "INFO"
    assert caplog.records[0].message == (
        "Backing up yum variable files from {} owned by {} packages.".format(
            " and ".join(action.yum_var_dirs), "centos"
        )
    )

    assert global_backup_control.push.call_count == expected_push_calls
    for path in paths:
        global_backup_control.push.assert_any_call(RestorableFile(path))

    assert caplog.records[-1].levelname == "INFO"
    assert caplog.records[-1].message == log_message


@pytest.mark.parametrize(
    "installed_pkgs, owned_files",
    [
        ([], []),
        (
            ["pkg1", "pkg2"],
            ["/etc/yum/vars/pkg1_var", "/etc/yum/vars/pkg2_var"],
        ),
    ],
)
def test_run(monkeypatch, installed_pkgs, owned_files, global_system_info, caplog):
    action = yum_variables.BackUpYumVariables()
    action._back_up_var_files = mock.Mock()

    global_system_info.repofile_pkgs = installed_pkgs
    monkeypatch.setattr(yum_variables, "system_info", global_system_info)

    class MockObj:
        def __init__(self, name):
            self.name = name

    mock_get_installed_pkg_objects = mock.Mock()
    mock_get_installed_pkg_objects.side_effect = lambda arg: [MockObj(pkg) for pkg in installed_pkgs if pkg == arg]
    monkeypatch.setattr(pkghandler, "get_installed_pkg_objects", mock_get_installed_pkg_objects)
    action._get_yum_var_files_owned_by_pkgs = mock.Mock()
    action._get_yum_var_files_owned_by_pkgs.return_value = owned_files

    action.run()

    assert caplog.records[0].is_task
    assert caplog.records[0].message == "Back up yum variables"
    assert "Getting a list of files owned by packages affecting variables in .repo files." in caplog.text
    assert "Packages affecting yum variables: {0}".format(", ".join(installed_pkgs)) in caplog.text
    action._back_up_var_files.assert_called_once_with(owned_files)
