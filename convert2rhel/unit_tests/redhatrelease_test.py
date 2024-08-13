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
import sys

import pytest
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))

from six.moves import mock

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import pkgmanager, redhatrelease, systeminfo, utils
from convert2rhel.redhatrelease import PkgManagerConf, get_system_release_filepath
from convert2rhel.systeminfo import system_info


PKG_MANAGER_CONF_WITHOUT_DISTROVERPKG = """[main]
installonly_limit=3

#  This is the default"""

PKG_MANAGER_CONF_WITH_DISTROVERPKG = """[main]
installonly_limit=3
distroverpkg=centos-release

#  This is the default"""


SUPPORTED_RHEL_VERSIONS = [7, 8]


@pytest.fixture()
def pkg_manager_conf_instance():
    return PkgManagerConf()


def test_get_pkg_manager_conf_content(monkeypatch):
    pkg_manager_conf = redhatrelease.PkgManagerConf(config_path=unit_tests.DUMMY_FILE)
    assert "Dummy file to read" in pkg_manager_conf._pkg_manager_conf_content


@pytest.mark.parametrize("version", SUPPORTED_RHEL_VERSIONS)
def test_patch_pkg_manager_conf_missing_distroverpkg(version, monkeypatch, pkg_manager_conf_instance):

    monkeypatch.setattr(system_info, "version", version)
    pkg_manager_conf = pkg_manager_conf_instance
    pkg_manager_conf._pkg_manager_conf_content = PKG_MANAGER_CONF_WITHOUT_DISTROVERPKG

    # Call just this function to avoid unmockable built-in write func
    pkg_manager_conf._comment_out_distroverpkg_tag()

    assert "distroverpkg=" not in pkg_manager_conf._pkg_manager_conf_content
    assert pkg_manager_conf._pkg_manager_conf_content.count("distroverpkg=") == 0


@pytest.mark.parametrize("version", SUPPORTED_RHEL_VERSIONS)
def test_patch_pkg_manager_conf_existing_distroverpkg(version, monkeypatch, pkg_manager_conf_instance):

    monkeypatch.setattr(system_info, "version", systeminfo.Version(version, 0))
    pkg_manager_conf = pkg_manager_conf_instance
    pkg_manager_conf._pkg_manager_conf_content = PKG_MANAGER_CONF_WITH_DISTROVERPKG

    # Call just this function to avoid unmockable built-in write func
    pkg_manager_conf._comment_out_distroverpkg_tag()

    assert "#distroverpkg=" in pkg_manager_conf._pkg_manager_conf_content
    assert pkg_manager_conf._pkg_manager_conf_content.count("#distroverpkg=") == 1


@pytest.mark.parametrize(
    ("pkg_type, subprocess_ret, expected_result"),
    (
        ("dnf", "S.5....T.  c /etc/dnf/dnf.conf", True),
        ("dnf", ".......T.  c /etc/dnf/dnf.conf", False),
        ("dnf", ".M.......  g /var/lib/dnf", False),
        ("yum", "S.5....T.  c /etc/yum.conf", True),
        ("yum", "", False),
        ("yum", ".......T.  c /etc/yum.conf", False),
        ("unknown", "anything", False),
    ),
)
def test_pkg_manager_is_modified(monkeypatch, pkg_type, subprocess_ret, expected_result):
    monkeypatch.setattr(pkgmanager, "TYPE", value=pkg_type)

    run_subprocess = unit_tests.RunSubprocessMocked(return_string=subprocess_ret)
    monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess)
    pkg_manager_conf = redhatrelease.PkgManagerConf()

    assert pkg_manager_conf.is_modified() == expected_result


@pytest.mark.parametrize("modified", (True, False))
def test_pkg_manager_patch(monkeypatch, modified, caplog, tmp_path):
    is_modified = mock.Mock(return_value=modified)
    monkeypatch.setattr(PkgManagerConf, "is_modified", value=is_modified)
    _comment_out_distroverpkg_tag = mock.Mock()
    monkeypatch.setattr(
        PkgManagerConf,
        "_comment_out_distroverpkg_tag",
        value=_comment_out_distroverpkg_tag,
    )
    monkeypatch.setattr(
        PkgManagerConf,
        "_pkg_manager_conf_path",
        value=tmp_path,
    )

    PkgManagerConf(config_path=str(tmp_path / "yum.conf")).patch()
    if modified:
        _comment_out_distroverpkg_tag.assert_called_once()
        assert "patched" in caplog.text
    else:
        _comment_out_distroverpkg_tag.assert_not_called()
        assert "Skipping patching, package manager configuration file has not been modified" in caplog.text


@pytest.mark.parametrize(("is_file", "exception"), ((True, False), (False, True)))
def test_get_system_release_filepath(is_file, exception, monkeypatch, caplog):
    is_file_mock = mock.MagicMock(return_value=is_file)
    monkeypatch.setattr(os.path, "isfile", value=is_file_mock)

    if exception:
        with pytest.raises(SystemExit):
            get_system_release_filepath()
        assert (
            "Error: Unable to find the /etc/system-release file containing the OS name and version"
            in caplog.records[-1].message
        )
    else:
        assert get_system_release_filepath() == "/etc/system-release"
