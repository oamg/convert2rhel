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
from convert2rhel.unit_tests.conftest import centos8


@pytest.mark.parametrize(
    ("path_exists", "expected"),
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
def test_get_rhel_repoids(pretend_os, path_exists, expected, monkeypatch):
    monkeypatch.setattr(os.path, "exists", value=lambda _: path_exists)
    repos = repo.get_rhel_repoids()
    assert repos == expected


@pytest.mark.parametrize(
    ("path_exists", "has_internet_access", "expected"),
    (
        (
            True,
            True,
            "/usr/share/convert2rhel/repos/centos-8.4",
        ),
        (
            False,
            False,
            None,
        ),
        (
            True,
            False,
            None,
        ),
        (
            False,
            True,
            None,
        ),
    ),
)
@centos8
def test_get_eus_repos_available(pretend_os, path_exists, has_internet_access, expected, monkeypatch):
    monkeypatch.setattr(os.path, "exists", value=lambda _: path_exists)
    monkeypatch.setattr(system_info, "has_internet_access", value=has_internet_access)

    assert repo.get_eus_repos_available() == expected


@pytest.mark.parametrize(("expected"), (("/usr/share/convert2rhel/repos/centos-8.4"),))
@centos8
def test_get_hardcoded_repofiles_dir(pretend_os, expected):
    assert repo._get_hardcoded_repofiles_dir() == expected
