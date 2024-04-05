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

__metaclass__ = type

import os

import pytest
import six

from convert2rhel import repo
from convert2rhel.unit_tests.conftest import all_systems, centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


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
def test_get_rhel_repoids_el8(pretend_os, is_eus_release, expected, monkeypatch):
    monkeypatch.setattr(repo.system_info, "eus_system", value=is_eus_release)
    repos = repo.get_rhel_repoids()
    assert repos == expected


@pytest.mark.parametrize(
    ("is_els_release", "expected"),
    (
        (
            True,
            [
                "rhel-7-server-els-rpms",
            ],
        ),
        (
            False,
            [
                "rhel-7-server-rpms",
            ],
        ),
    ),
)
@centos7
def test_get_rhel_repoids_el7(pretend_os, is_els_release, expected, monkeypatch):
    monkeypatch.setattr(repo.system_info, "els_system", value=is_els_release)
    repos = repo.get_rhel_repoids()
    assert repos == expected


@pytest.mark.parametrize(("enablerepo", "disablerepos"), (([], ["rhel*"]), (["test-repo"], ["rhel*", "test-repo"])))
def test_get_rhel_repos_to_disable(monkeypatch, enablerepo, disablerepos):
    monkeypatch.setattr(repo.tool_opts, "enablerepo", enablerepo)

    repos = repo.get_rhel_repos_to_disable()

    assert repos == disablerepos


@pytest.mark.parametrize(
    ("disable_repos", "command"),
    (
        ([], ""),
        (["test-repo"], "--disablerepo=test-repo"),
        (["rhel*", "test-repo"], "--disablerepo=rhel* --disablerepo=test-repo"),
    ),
)
def test_get_rhel_disable_repos_command(disable_repos, command):
    output = repo.get_rhel_disable_repos_command(disable_repos)

    assert output == command
