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
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from collections import namedtuple

from six.moves import mock

from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel import pkgmanager, redhatrelease, utils
from convert2rhel.redhatrelease import YumConf, get_system_release_filepath
from convert2rhel.systeminfo import system_info


YUM_CONF_WITHOUT_DISTROVERPKG = """[main]
installonly_limit=3

#  This is the default"""

YUM_CONF_WITH_DISTROVERPKG = """[main]
installonly_limit=3
distroverpkg=centos-release

#  This is the default"""


SUPPORTED_RHEL_VERSIONS = [6, 7, 8]


class DumbMocked(unit_tests.MockFunction):
    def __call__(self, *args, **kwargs):
        pass


class GlobMocked(unit_tests.MockFunction):
    def __call__(self, *args, **kwargs):
        return [
            unit_tests.TMP_DIR + "redhat-release/pkg1.rpm",
            unit_tests.TMP_DIR + "redhat-release/pkg2.rpm",
            "Server/redhat-release-7/pkg1.rpm",
            "Server/redhat-release-7/pkg2.rpm",
        ]


class RunSubprocessMocked(unit_tests.MockFunction):
    def __init__(self):
        self.cmd = None

    def __call__(self, cmd, print_cmd=True, print_output=True):
        self.cmd = cmd
        return "Test output", 0


def test_get_yum_conf_content(monkeypatch):
    monkeypatch.setattr(redhatrelease.YumConf, "_yum_conf_path", unit_tests.DUMMY_FILE)

    yum_conf = redhatrelease.YumConf()

    assert "Dummy file to read" in yum_conf._yum_conf_content


@pytest.mark.parametrize("version", SUPPORTED_RHEL_VERSIONS)
def test_patch_yum_conf_missing_distroverpkg(version, monkeypatch):
    monkeypatch.setattr(redhatrelease.YumConf, "_yum_conf_path", unit_tests.DUMMY_FILE)
    monkeypatch.setattr(system_info, "version", version)
    yum_conf = redhatrelease.YumConf()
    yum_conf._yum_conf_content = YUM_CONF_WITHOUT_DISTROVERPKG

    # Call just this function to avoid unmockable built-in write func
    yum_conf._comment_out_distroverpkg_tag()

    assert "distroverpkg=" not in yum_conf._yum_conf_content
    assert yum_conf._yum_conf_content.count("distroverpkg=") == 0


@pytest.mark.parametrize("version", SUPPORTED_RHEL_VERSIONS)
def test_patch_yum_conf_existing_distroverpkg(version, monkeypatch):
    monkeypatch.setattr(redhatrelease.YumConf, "_yum_conf_path", unit_tests.DUMMY_FILE)
    monkeypatch.setattr(system_info, "version", namedtuple("Version", ["major", "minor"])(version, 0))
    yum_conf = redhatrelease.YumConf()
    yum_conf._yum_conf_content = YUM_CONF_WITH_DISTROVERPKG

    # Call just this function to avoid unmockable built-in write func
    yum_conf._comment_out_distroverpkg_tag()

    assert "#distroverpkg=" in yum_conf._yum_conf_content
    assert yum_conf._yum_conf_content.count("#distroverpkg=") == 1


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
def test_yum_is_modified(monkeypatch, pkg_type, subprocess_ret, expected_result):
    monkeypatch.setattr(pkgmanager, "TYPE", value=pkg_type)

    run_subprocess = mock.Mock(return_value=(subprocess_ret, "anything"))
    monkeypatch.setattr(utils, "run_subprocess", value=run_subprocess)

    assert YumConf.is_modified() == expected_result


@pytest.mark.parametrize("modified", (True, False))
def test_yum_patch(monkeypatch, modified, caplog):
    is_modified = mock.Mock(return_value=modified)
    monkeypatch.setattr(YumConf, "is_modified", value=is_modified)
    _comment_out_distroverpkg_tag = mock.Mock()
    monkeypatch.setattr(
        YumConf,
        "_comment_out_distroverpkg_tag",
        value=_comment_out_distroverpkg_tag,
    )
    _write_altered_yum_conf = mock.Mock()
    monkeypatch.setattr(YumConf, "_write_altered_yum_conf", value=_write_altered_yum_conf)

    YumConf().patch()

    if modified:
        _comment_out_distroverpkg_tag.assert_called_once()
        assert "patched" in caplog.text
    else:
        _comment_out_distroverpkg_tag.assert_not_called()
        assert "Skipping patching, yum configuration file not modified" in caplog.text


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
