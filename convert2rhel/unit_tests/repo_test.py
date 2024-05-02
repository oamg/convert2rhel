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


import pytest

from convert2rhel import repo
from convert2rhel.unit_tests.conftest import centos8


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
    monkeypatch.setattr(repo.system_info, "eus_system", value=is_eus_release)
    repos = repo.get_rhel_repoids()
    assert repos == expected
