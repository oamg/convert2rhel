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
import six

from convert2rhel import breadcrumbs, pkghandler, pkgmanager, utils
from convert2rhel.unit_tests import create_pkg_information, create_pkg_obj
from convert2rhel.unit_tests.conftest import centos7


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def _mock_pkg_obj():
    return create_pkg_obj(name="convert2rhel", epoch=1, version="2", release="3", arch="x86_64")


@pytest.fixture
def _mock_pkg_information():
    return create_pkg_information(
        name="convert2rhel",
        epoch="1",
        version="2",
        release="3",
        arch="x86_64",
        signature="73bde98381b46521",
    )


@centos7
def test_collect_early_data(pretend_os, _mock_pkg_obj, _mock_pkg_information, monkeypatch):
    monkeypatch.setattr(pkgmanager, "TYPE", "yum")
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_pkg_object", _mock_pkg_obj)
    monkeypatch.setattr(pkghandler, "get_installed_pkg_objects", lambda name: [_mock_pkg_obj])
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda name: [_mock_pkg_information])
    breadcrumbs.breadcrumbs.collect_early_data()

    # Asserting that the populated fields are not null (or None), the value
    # checks for them is actually checked in their individual unit_tests.
    assert breadcrumbs.breadcrumbs.signature != "null"
    assert breadcrumbs.breadcrumbs.source_os != "null"
    assert breadcrumbs.breadcrumbs.nevra != "null"
    assert breadcrumbs.breadcrumbs.executed != "null"
    assert breadcrumbs.breadcrumbs.activity_started != "null"
    assert breadcrumbs.breadcrumbs._pkg_object is not None


@pytest.mark.parametrize(
    ("success"),
    (
        (False),
        (True),
    ),
)
@centos7
def test_finish_collection(pretend_os, success, monkeypatch):
    save_migration_results_mock = mock.Mock()
    save_rhsm_facts_mock = mock.Mock()

    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_save_migration_results", save_migration_results_mock)
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_save_rhsm_facts", save_rhsm_facts_mock)
    # Set to true, pretend that user was informed about collecting data
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_inform_telemetry", True)

    breadcrumbs.breadcrumbs.finish_collection(success=success)

    if success:
        assert breadcrumbs.breadcrumbs.success
        assert breadcrumbs.breadcrumbs.target_os != "null"
    else:
        assert not breadcrumbs.breadcrumbs.success
        assert breadcrumbs.breadcrumbs.target_os == "null"

    assert save_migration_results_mock.call_count == 1
    assert save_rhsm_facts_mock.call_count == 1


@pytest.mark.parametrize(
    ("command", "expected"),
    (
        (
            [
                "/usr/bin/convert2rhel",
                "--username=test",
                "--password=nicePassword",
            ],
            "/usr/bin/convert2rhel --username=***** --password=*****",
        ),
        (
            ["/usr/bin/convert2rhel", "-u=test", "-p=nicePassword"],
            "/usr/bin/convert2rhel -u=***** -p=*****",
        ),
        (
            [
                "/usr/bin/convert2rhel",
                "--activationkey=test",
                "--org=1234",
                "-y",
            ],
            "/usr/bin/convert2rhel --activationkey=***** --org=***** -y",
        ),
        (
            ["/usr/bin/convert2rhel", "-k=test", "-o=1234", "-y"],
            "/usr/bin/convert2rhel -k=***** -o=***** -y",
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

    assert {
        "CONVERT2RHEL_": "VALUE1",
        "CONVERT2RHEL_VAR": "VALUE2",
    } == breadcrumbs.breadcrumbs.env


@pytest.mark.parametrize(
    ("file", "content", "key", "out"),
    [
        (False, None, "key", '{"key":[{"some_key": "some_data"}]}'),
        (True, '{"key":[]}', "key", '{"key":[{"some_key": "some_data"}]}'),
        (
            True,
            '{"diff_key":[]}',
            "key",
            '{"diff_key":[], "key":[{"some_key": "some_data"}]}',
        ),
        (True, "something", "key", False),
    ],
)
def test_write_obj_to_array_json(tmpdir, file, content, key, out):
    new_obj = {"some_key": "some_data"}
    path = tmpdir.mkdir("test_write_obj_to_array_json").join("migration-results")

    if file:
        path.write(content)

    breadcrumbs._write_obj_to_array_json(str(path), new_obj, key)

    if content == "something":
        # check, if the text is still there and the json was appended
        assert "something" in path.read()
        assert "key" in path.read()
    else:
        assert sorted(json.loads(path.read())) == sorted(json.loads(out))


@centos7
def test_save_rhsm_facts(pretend_os, monkeypatch, tmpdir, caplog):
    rhsm_file = str(tmpdir.join("convert2rhel.facts"))
    monkeypatch.setattr(breadcrumbs, "RHSM_CUSTOM_FACTS_FOLDER", str(tmpdir))
    monkeypatch.setattr(
        breadcrumbs,
        "RHSM_CUSTOM_FACTS_FILE",
        rhsm_file,
    )

    breadcrumbs.breadcrumbs._save_rhsm_facts()
    assert "Writing RHSM custom facts to '%s'" % rhsm_file in caplog.records[-1].message


def test_save_rhsm_facts_no_rhsm_folder(monkeypatch, tmpdir, caplog):
    rhsm_folder = str(tmpdir.join("rhsm").join("facts"))
    rhsm_file = "%s/convert2rhel.facts" % rhsm_folder
    monkeypatch.setattr(breadcrumbs, "RHSM_CUSTOM_FACTS_FOLDER", rhsm_folder)
    monkeypatch.setattr(breadcrumbs, "RHSM_CUSTOM_FACTS_FILE", rhsm_file)

    breadcrumbs.breadcrumbs._save_rhsm_facts()
    assert "No RHSM facts folder found at '%s'." % rhsm_folder in caplog.records[-2].message
    assert "Writing RHSM custom facts to '%s'" % rhsm_file in caplog.records[-1].message


def test_save_migration_results(tmpdir, monkeypatch, caplog):
    migration_results = str(tmpdir.join("migration-results"))
    write_obj_to_array_json_mock = mock.Mock()
    monkeypatch.setattr(breadcrumbs, "MIGRATION_RESULTS_FILE", migration_results)
    monkeypatch.setattr(breadcrumbs, "_write_obj_to_array_json", write_obj_to_array_json_mock)

    breadcrumbs.breadcrumbs._save_migration_results()

    assert "Writing breadcrumbs to '%s'." % migration_results in caplog.records[-1].message
    assert write_obj_to_array_json_mock.call_count == 1


def test_set_pkg_object(_mock_pkg_obj, monkeypatch):
    monkeypatch.setattr(pkghandler, "get_installed_pkg_objects", lambda name: [_mock_pkg_obj])
    breadcrumbs.breadcrumbs._set_pkg_object()
    assert breadcrumbs.breadcrumbs._pkg_object.name == "convert2rhel"


@pytest.mark.skipif(
    pkgmanager.TYPE != "dnf",
    reason="No dnf module detected on the system, skipping it.",
)
def test_set_nevra_dnf(monkeypatch, _mock_pkg_obj):
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_pkg_object", _mock_pkg_obj)
    breadcrumbs.breadcrumbs._set_nevra()

    assert breadcrumbs.breadcrumbs.nevra == "convert2rhel-1:2-3.x86_64"


@pytest.mark.skipif(
    pkgmanager.TYPE != "yum",
    reason="No yum module detected on the system, skipping it.",
)
def test_set_nevra_yum(monkeypatch, _mock_pkg_obj):
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_pkg_object", _mock_pkg_obj)
    breadcrumbs.breadcrumbs._set_nevra()

    assert breadcrumbs.breadcrumbs.nevra == "1:convert2rhel-2-3.x86_64"


def test_set_nevra_dnf(monkeypatch, _mock_pkg_obj):
    monkeypatch.setattr(pkgmanager, "TYPE", "dnf")
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_pkg_object", _mock_pkg_obj)
    breadcrumbs.breadcrumbs._set_nevra()

    assert breadcrumbs.breadcrumbs.nevra == "convert2rhel-1:2-3.x86_64"


def test_set_signature(monkeypatch, _mock_pkg_obj, _mock_pkg_information):
    monkeypatch.setattr(pkgmanager, "TYPE", "yum")
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_pkg_object", _mock_pkg_obj)
    monkeypatch.setattr(pkghandler, "get_installed_pkg_information", lambda name: [_mock_pkg_information])
    breadcrumbs.breadcrumbs._set_signature()
    assert "73bde98381b46521" in breadcrumbs.breadcrumbs.signature


def test_set_started():
    breadcrumbs.breadcrumbs._set_started()
    assert "Z" in breadcrumbs.breadcrumbs.activity_started


def test_set_ended():
    breadcrumbs.breadcrumbs._set_ended()
    assert "Z" in breadcrumbs.breadcrumbs.activity_ended


@centos7
def test_set_source_os(pretend_os):
    breadcrumbs.breadcrumbs._set_source_os()
    assert {
        "id": "null",
        "name": "CentOS Linux",
        "version": "7.9",
    } == breadcrumbs.breadcrumbs.source_os


@centos7
def test_set_target_os(pretend_os):
    breadcrumbs.breadcrumbs._set_target_os()
    assert {
        "id": "null",
        "name": "CentOS Linux",
        "version": "7.9",
    } == breadcrumbs.breadcrumbs.target_os


@pytest.mark.parametrize(("telemetry_disabled", "telemetry_called"), [(True, 0), (False, 1)])
def test_disable_telemetry(telemetry_disabled, telemetry_called, monkeypatch):
    if telemetry_disabled:
        monkeypatch.setenv("CONVERT2RHEL_DISABLE_TELEMETRY", "1")

    _save_migration_results = mock.Mock()
    _save_rhsm_facts = mock.Mock()

    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_save_migration_results", _save_migration_results)
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_save_rhsm_facts", _save_rhsm_facts)
    # Set to true, pretend that user was informed about collecting data
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_inform_telemetry", True)

    breadcrumbs.breadcrumbs.finish_collection()

    assert _save_migration_results.call_count == 1
    assert _save_rhsm_facts.call_count == telemetry_called


def test_user_not_informed_about_telemetry(monkeypatch):
    _save_migration_results = mock.Mock()
    _save_rhsm_facts = mock.Mock()

    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_save_migration_results", _save_migration_results)
    monkeypatch.setattr(breadcrumbs.breadcrumbs, "_save_rhsm_facts", _save_rhsm_facts)

    breadcrumbs.breadcrumbs.finish_collection()

    _save_migration_results.assert_called_once()
    _save_rhsm_facts.assert_not_called()


@pytest.mark.parametrize(("telemetry_disabled", "call_count"), [(True, 0), (False, 1)])
def test_print_data_collection(telemetry_disabled, call_count, monkeypatch, caplog):
    if telemetry_disabled:
        monkeypatch.setenv("CONVERT2RHEL_DISABLE_TELEMETRY", "1")

    ask_to_continue = mock.Mock()
    monkeypatch.setattr(utils, "ask_to_continue", ask_to_continue)

    breadcrumbs.breadcrumbs.print_data_collection()

    ask_to_continue.call_count == call_count

    if telemetry_disabled:
        assert "Skipping, telemetry disabled." in caplog.records[-1].message
