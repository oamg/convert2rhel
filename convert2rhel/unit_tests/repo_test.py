# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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

import os

import pytest

from convert2rhel import repo
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests.conftest import all_systems, centos8


@pytest.mark.parametrize(
    ("is_eus_release", "expected"),
    (
        (
            True,
            [
                "rhel-8-for-x86_64-baseos-eus-rpms",
                "rhel-8-for-x86_64-appstream-eus-rpms",
            ],
        ),
        (
            False,
            [
                "rhel-8-for-x86_64-baseos-rpms",
                "rhel-8-for-x86_64-appstream-rpms",
            ],
        ),
    ),
)
@centos8
def test_get_rhel_repoids(pretend_os, is_eus_release, expected, monkeypatch):
    monkeypatch.setattr(repo.system_info, "corresponds_to_rhel_eus_release", value=lambda: is_eus_release)
    repos = repo.get_rhel_repoids()
    assert repos == expected


@pytest.mark.parametrize(
    ("path_exists", "expected"),
    (
        (
            True,
            "/usr/share/convert2rhel/repos/centos-8.4",
        ),
        (
            False,
            None,
        ),
        (
            False,
            None,
        ),
    ),
)
@centos8
def test_get_hardcoded_repofiles_dir(pretend_os, path_exists, expected, monkeypatch):
    monkeypatch.setattr(os.path, "exists", value=lambda _: path_exists)
    assert repo.get_hardcoded_repofiles_dir() == expected


@pytest.fixture
def generate_vars_dir(tmpdir):
    tmpdir = tmpdir.mkdir("etc")
    yum_vars = tmpdir.mkdir("yum").mkdir("vars").join("yum_test_var")
    dnf_vars = tmpdir.mkdir("dnf").mkdir("vars").join("dnf_test_var")
    yum_vars.write("test_var")
    dnf_vars.write("test_var")

    return str(dnf_vars), str(yum_vars)


@pytest.fixture
def generate_backup_vars_dir(tmpdir):
    # Same idea as `generate_vars_dir`, but for backup to test restore.
    tmpdir = tmpdir.mkdir("backup")
    yum_vars = tmpdir.mkdir("yum").mkdir("vars").join("yum_test_var")
    dnf_vars = tmpdir.mkdir("dnf").mkdir("vars").join("dnf_test_var")
    yum_vars.write("test_var")
    dnf_vars.write("test_var")

    return str(dnf_vars), str(yum_vars)


@pytest.mark.parametrize(
    ("create_backup_dirs"),
    (
        (True),
        (False),
    ),
)
@all_systems
def test_backup_varsdir(pretend_os, create_backup_dirs, generate_vars_dir, tmpdir, caplog):
    dnf_vars_dir, yum_vars_dir = generate_vars_dir
    repo.DEFAULT_DNF_VARS_DIR = os.path.dirname(dnf_vars_dir)
    repo.DEFAULT_YUM_VARS_DIR = os.path.dirname(yum_vars_dir)
    tmpdir = tmpdir.mkdir("backup")
    if create_backup_dirs:
        tmpdir.mkdir("dnf").mkdir("vars")
        tmpdir.mkdir("yum").mkdir("vars")

    repo.BACKUP_DIR = str(tmpdir)

    repo.backup_varsdir()
    assert "Backed up variable file" in caplog.records[-1].message


@all_systems
def test_backup_varsdir_without_variables(pretend_os, generate_vars_dir, tmpdir, caplog):
    dnf_vars_dir, yum_vars_dir = generate_vars_dir
    repo.DEFAULT_DNF_VARS_DIR = os.path.dirname(dnf_vars_dir)
    repo.DEFAULT_YUM_VARS_DIR = os.path.dirname(yum_vars_dir)
    repo.BACKUP_DIR = str(tmpdir)

    os.remove(dnf_vars_dir)
    os.remove(yum_vars_dir)

    repo.backup_varsdir()
    assert "No variables files backed up." in caplog.records[-1].message


@all_systems
def test_restore_varsdir(pretend_os, generate_backup_vars_dir, generate_vars_dir, tmpdir, caplog):
    dnf_vars_dir, yum_vars_dir = generate_vars_dir

    repo.DEFAULT_DNF_VARS_DIR = os.path.dirname(dnf_vars_dir)
    repo.DEFAULT_YUM_VARS_DIR = os.path.dirname(yum_vars_dir)
    os.remove(dnf_vars_dir)
    os.remove(yum_vars_dir)

    repo.BACKUP_DIR = os.path.join(str(tmpdir), "backup")

    repo.restore_varsdir()
    assert "Restored variable file" in caplog.records[-1].message


@all_systems
def test_restore_varsdir_without_variables(pretend_os, generate_backup_vars_dir, generate_vars_dir, tmpdir, caplog):
    dnf_vars_dir, yum_vars_dir = generate_vars_dir
    backup_dnf_var, backup_yum_var = generate_backup_vars_dir

    repo.DEFAULT_DNF_VARS_DIR = os.path.dirname(dnf_vars_dir)
    repo.DEFAULT_YUM_VARS_DIR = os.path.dirname(yum_vars_dir)
    repo.BACKUP_DIR = os.path.join(str(tmpdir), "backup")

    os.remove(backup_dnf_var)
    os.remove(backup_yum_var)

    repo.restore_varsdir()
    assert "No varaibles files to rollback" in caplog.records[-1].message


@centos8
def test_restore_varsdir_without_backup(pretend_os, tmpdir, caplog):
    repo.BACKUP_DIR = str(tmpdir)

    repo.restore_varsdir()
    assert "Couldn't find backup directory at" in caplog.records[-1].message
