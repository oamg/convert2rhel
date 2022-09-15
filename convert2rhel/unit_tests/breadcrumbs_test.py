# -*- coding: utf-8 -*-
#
# Copyright(C) 2021 Red Hat, Inc.
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

import json

import pytest

from convert2rhel import breadcrumbs


@pytest.mark.parametrize(
    ("command", "expected"),
    (
        (
            ["/usr/bin/convert2rhel", "--username=test", "--password=nicePassword"],
            "/usr/bin/convert2rhel --username=test --password=*****",
        ),
        (
            ["/usr/bin/convert2rhel", "-u=test", "-p=nicePassword"],
            "/usr/bin/convert2rhel -u=test -p=*****",
        ),
        (
            ["/usr/bin/convert2rhel", "--activationkey=test", "--org=1234", "-y"],
            "/usr/bin/convert2rhel --activationkey=***** --org=1234 -y",
        ),
        (
            ["/usr/bin/convert2rhel", "-k=test", "-o=1234", "-y"],
            "/usr/bin/convert2rhel -k=***** -o=1234 -y",
        ),
    ),
)
def test_set_executed(command, expected, monkeypatch):
    monkeypatch.setattr(breadcrumbs.sys, "argv", command)
    breadcrumbs.breadcrumbs._set_executed()

    assert breadcrumbs.breadcrumbs.executed == expected


def test_set_env(monkeypatch):
    monkeypatch.setenv("CONVERT2RHEL_", "VALUE1")
    monkeypatch.setenv("CONVERT2RHEL_VAR", "VALUE2")
    monkeypatch.setenv("NOTCONVERT2RHEL_", "VALUE3")
    monkeypatch.setenv("RANDOM_VAR", "VALUE4")

    breadcrumbs.breadcrumbs._set_env()

    assert {"CONVERT2RHEL_": "VALUE1", "CONVERT2RHEL_VAR": "VALUE2"} == breadcrumbs.breadcrumbs.env


@pytest.mark.parametrize(
    ("file", "content", "out"),
    [
        (False, None, '{"key":[{"some_key": "some_data"}]}'),
        (True, '{"key":[]}', '{"key":[{"some_key": "some_data"}]}'),
        (True, '{"diff_key":[]}', '{"diff_key":[], "key":[{"some_key": "some_data"}]}'),
        (True, "something", False),
    ],
)
def test_write_obj_to_array_json(tmpdir, file, content, out):
    new_obj = {"some_key": "some_data"}
    path = tmpdir.mkdir("test_write_obj_to_array_json").join("migration-results")

    if file:
        path.write(content)

    breadcrumbs.write_obj_to_array_json(str(path), new_obj, "key")

    print(path.read())

    if content == "something":
        # check, if the text is still there and the json was appended
        assert "something" in path.read()
        assert "key" in path.read()
    else:
        assert sorted(json.loads(path.read())) == sorted(json.loads(out))
