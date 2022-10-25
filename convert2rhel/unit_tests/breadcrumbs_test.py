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


def test_sanitize_cli_options():
    options_to_sanitize = frozenset(("--password", "-p", "--activationkey", "-k"))

    io = [
        (
            ["convert2rhel", "--password=123", "--another"],
            "convert2rhel --password=*** --another",
        ),
        (["convert2rhel", "-p", "123", "--another"], "convert2rhel -p *** --another"),
        (["convert2rhel", "-k", "123", "--another"], "convert2rhel -k *** --another"),
        (["convert2rhel", "--another", "-k"], "convert2rhel --another -k"),
        (
            ["convert2rhel", "--argument", "with space in it", "--another"],
            'convert2rhel --argument "with space in it" --another',
        ),
        (
            ["convert2rhel", "--argument=with space in it", "--another"],
            'convert2rhel --argument="with space in it" --another',
        ),
    ]

    for (inp, outp) in io:
        assert breadcrumbs.sanitize_cli_options(inp, options_to_sanitize) == outp


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
