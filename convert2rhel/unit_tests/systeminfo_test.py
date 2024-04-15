# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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

import logging
import os
import time

import pytest
import six

from convert2rhel import logger, systeminfo, utils
from convert2rhel.systeminfo import RELEASE_VER_MAPPING, Version, system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import RunSubprocessMocked
from convert2rhel.unit_tests.conftest import all_systems, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock, urllib


@pytest.fixture(autouse=True)
def register_system_info_logger(monkeypatch):
    # Have to initialize the logger since we are not constructing the
    # system_info object properly i.e: we are not calling `resolve_system_info()`
    monkeypatch.setattr(system_info, "logger", logging.getLogger(__name__))


class TestRPMFilesDiff:
    def test_modified_rpm_files_diff_with_no_rpm_va(self, monkeypatch):
        monkeypatch.setattr(tool_opts, "no_rpm_va", mock.Mock(return_value=True))
        assert system_info.modified_rpm_files_diff() is None

    def test_modified_rpm_files_diff_without_differences_after_conversion(self, monkeypatch):
        monkeypatch.setattr(system_info, "generate_rpm_va", mock.Mock())
        monkeypatch.setattr(utils, "get_file_content", mock.Mock(side_effect=(["rpm1", "rpm2"], ["rpm1", "rpm2"])))

        assert system_info.modified_rpm_files_diff() is None

    def test_modified_rpm_files_diff_with_differences_after_conversion(self, monkeypatch, caplog):
        monkeypatch.setattr(system_info, "generate_rpm_va", mock.Mock())
        monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=True))
        monkeypatch.setattr(tool_opts, "no_rpm_va", False)
        monkeypatch.setattr(
            utils,
            "get_file_content",
            mock.Mock(
                side_effect=(
                    [".M.......  g /etc/pki/ca-trust/extracted/java/cacerts"],
                    [
                        ".M.......  g /etc/pki/ca-trust/extracted/java/cacerts",
                        "S.5....T.  c /etc/yum.conf",
                    ],
                )
            ),
        )

        system_info.modified_rpm_files_diff()

        assert any("S.5....T.  c /etc/yum.conf" in elem.message for elem in caplog.records if elem.levelname == "INFO")


class TestGenerateRPMVA:
    def test_generate_rpm_va(self, global_tool_opts, monkeypatch, tmpdir):
        global_tool_opts.no_rpm_va = False
        monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string="rpmva\n"))
        monkeypatch.setattr(logger, "LOG_DIR", str(tmpdir))
        rpmva_output_file = str(tmpdir / "rpm_va.log")

        system_info.generate_rpm_va()

        # Check that rpm -Va is executed (default)
        assert utils.run_subprocess.called
        assert utils.run_subprocess.call_args_list[0][0][0] == ["rpm", "-Va"]

        # Check that the output was stored into the specific file.
        assert os.path.isfile(rpmva_output_file)
        assert utils.get_file_content(rpmva_output_file) == "rpmva\n"

    def test_generate_rpm_va_skip(self, global_tool_opts, monkeypatch, tmpdir):
        global_tool_opts.no_rpm_va = True
        monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())
        monkeypatch.setattr(logger, "LOG_DIR", str(tmpdir))
        rpmva_output_file = str(tmpdir / "rpm_va.log")

        system_info.generate_rpm_va()

        # Check that rpm -Va is not called when the --no-rpm-va option is used.
        assert not utils.run_subprocess.called
        assert not os.path.exists(rpmva_output_file)


@pytest.mark.parametrize(
    ("pkg_name", "present_on_system", "expected_return"),
    [
        ("package A", True, True),
        ("package A", False, False),
        ("", None, False),
    ],
)
def test_system_info_has_rpm(pkg_name, present_on_system, expected_return, monkeypatch):
    run_subprocess_mocked = RunSubprocessMocked(return_value=("", 0) if present_on_system else ("", 1))
    monkeypatch.setattr(systeminfo, "run_subprocess", value=run_subprocess_mocked)
    assert system_info.is_rpm_installed(pkg_name) == expected_return
    assert run_subprocess_mocked.called


@all_systems
def test_get_release_ver(pretend_os):
    """Test if all pretended OSes presented in theh RELEASE_VER_MAPPING."""
    assert system_info.releasever in RELEASE_VER_MAPPING.values()


@pytest.mark.parametrize(
    ("side_effect", "expected", "message"),
    (
        (urllib.error.URLError(reason="fail"), False, "Failed to retrieve data from host"),
        (None, True, "internet connection seems to be available"),
    ),
)
def test_check_internet_access(side_effect, expected, message, monkeypatch, caplog):
    monkeypatch.setattr(
        systeminfo.urllib.request,
        "urlopen",
        mock.Mock(side_effect=side_effect),
    )

    assert system_info._check_internet_access() == expected
    assert message in caplog.records[-1].message


@pytest.mark.parametrize(
    ("version_major", "command_output", "expected_command", "expected_output"),
    (
        (7, "ActiveState=active\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], True),
        (7, "ActiveState=reloading\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], False),
        (7, "ActiveState=inactive\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], False),
        (7, "ActiveState=failed\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], False),
        (8, "ActiveState=active\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], True),
        (8, "ActiveState=inactive\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], False),
        # Note: systemctl seems to emit ActiveState=something in all reasonable situations.
        # So these just test that we do something reasonable if things are totally messed up.
        (8, "Fruuble\nBarble\n", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], False),
        (8, "", ["/usr/bin/systemctl", "show", "-p", "ActiveState", "dbus"], False),
    ),
)
def test_get_dbus_status(monkeypatch, version_major, command_output, expected_command, expected_output):
    monkeypatch.setattr(system_info, "version", Version(version_major, 0))
    monkeypatch.setattr(time, "sleep", mock.Mock)
    run_subprocess_mocked = RunSubprocessMocked(return_string=command_output)
    monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

    assert system_info._is_dbus_running() == expected_output
    run_subprocess_mocked.assert_called_with(expected_command, print_output=mock.ANY)


@pytest.mark.parametrize(
    ("states", "expected"),
    (
        (
            (
                "reloading",
                "active",
            ),
            True,
        ),
        (
            (
                "activating",
                "activating",
                "active",
            ),
            True,
        ),
        (
            (
                "activating",
                "failed",
            ),
            False,
        ),
        (
            (
                "deactivating",
                "deactivated",
            ),
            False,
        ),
    ),
)
def test_get_dbus_status_in_progress(monkeypatch, states, expected):
    """Test that dbus switching from reloading or activating to active is detected."""
    monkeypatch.setattr(system_info, "version", Version(8, 0))
    monkeypatch.setattr(time, "sleep", mock.Mock)

    side_effects = []
    for state in states:
        side_effects.append(("ActiveState=%s\n" % state, 0))

    run_subprocess_mocked = RunSubprocessMocked(side_effect=side_effects)
    monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

    assert system_info._is_dbus_running() is expected


@pytest.mark.parametrize(
    ("major", "minor", "expected"),
    (
        (7, 9, False),
        (8, 5, False),
        (8, 6, True),
        (8, 7, False),
        (8, 8, False),  # Change expected to true after eus_release date
        (8, 9, False),
    ),
)
def test_corresponds_to_rhel_eus_release(major, minor, expected, monkeypatch):
    version = Version(major, minor)
    monkeypatch.setattr(system_info, "version", version)

    assert system_info.corresponds_to_rhel_eus_release() == expected


@pytest.mark.parametrize(
    ("major", "minor", "expected"),
    (
        (7, 9, False),
        (8, 5, False),
        (8, 6, True),
        (8, 7, False),
        (8, 8, True),
        (8, 9, False),
    ),
)
def test_corresponds_to_rhel_eus_release_eus_override(major, minor, expected, monkeypatch, global_tool_opts):
    version = Version(major, minor)
    monkeypatch.setattr(system_info, "version", version)
    monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
    global_tool_opts.eus = True
    assert system_info.corresponds_to_rhel_eus_release() == expected


@pytest.mark.parametrize(
    ("system_release_content", "key", "value"),
    (
        ("CentOS Linux release 8.1.1911 (Core)", "distribution_id", "Core"),
        ("Oracle Linux Server release 7.8", "name", "Oracle Linux Server"),
        ("Oracle Linux Server release 7.8", "distribution_id", None),
        ("CentOS Stream release 8", "id", "centos"),
        ("CentOS Linux release 8.1.1911 (Core)", "version", Version(8, 1)),
        ("CentOS Stream release 8", "version", Version(8, 10)),
        ("Red Hat Enterprise Linux release 8.10 Beta (Ootpa)", "version", Version(8, 10)),
    ),
)
def test_parse_system_release_content_from_string(system_release_content, key, value):
    parsed = system_info.parse_system_release_content(system_release_content)
    assert parsed[key] == value


def test_fail_to_parse_system_release_content_from_string():
    system_release_content = "Non-matching string"
    parsed = system_info.parse_system_release_content(system_release_content)
    assert not parsed


@pytest.mark.parametrize(
    (
        "submgr_enabled_repos",
        "tool_opts_no_rhsm",
        "tool_opts_enablerepo",
        "expected",
    ),
    (
        (
            ["rhel-repo1.repo", "rhel-repo2.repo"],
            False,
            [],
            ["rhel-repo1.repo", "rhel-repo2.repo"],
        ),
        (
            ["rhel-repo1.repo", "rhel-repo2.repo"],
            True,
            ["cli-rhel-repo1.repo", "cli-rhel-repo2.repo"],
            ["cli-rhel-repo1.repo", "cli-rhel-repo2.repo"],
        ),
    ),
)
def test_get_enabled_rhel_repos(
    submgr_enabled_repos,
    tool_opts_no_rhsm,
    tool_opts_enablerepo,
    expected,
    global_tool_opts,
    monkeypatch,
):
    monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
    monkeypatch.setattr(system_info, "submgr_enabled_repos", submgr_enabled_repos)
    global_tool_opts.enablerepo = tool_opts_enablerepo
    global_tool_opts.no_rhsm = tool_opts_no_rhsm

    assert system_info.get_enabled_rhel_repos() == expected


@centos8
def test_print_system_information(pretend_os, caplog):
    system_info.print_system_information()

    assert "CentOS Linux" in caplog.records[-4].message
    assert "8.5" in caplog.records[-3].message
    assert "x86_64" in caplog.records[-2].message
    assert "centos-8-x86_64.cfg" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("file_content", "expected", "message"),
    (
        (
            """
[system_info]
swap_pkgs =
  centos-logos | redhat-logos
  centos-indexhtml | redhat-indexhtml

""",
            {"centos-indexhtml": "redhat-indexhtml", "centos-logos": "redhat-logos"},
            "",
        ),
        (
            """
[system_info]
swap_pkgs =
""",
            {},
            "Leaving the swap package list empty. No packages defined.",
        ),
        (
            """
[system_info]
swap_pkgs =
    centos-logos | redhat-logos
    centos-logos | redhat-logos2
""",
            {"centos-logos": "redhat-logos2"},
            "Old package centos-logos will be swapped by redhat-logos2 instead of redhat-logos.",
        ),
        (
            """
[system_info]
""",
            {},
            "Leaving the swap package list empty. Missing swap_pkgs key in configuration file.",
        ),
    ),
)
def test_get_swap_pkgs(monkeypatch, file_content, tmpdir, expected, message, caplog):
    cfg_filename = "test.cfg"
    cfg_path = tmpdir.mkdir("configs").join(cfg_filename)
    cfg_path.write(file_content)

    monkeypatch.setattr(utils, "DATA_DIR", str(tmpdir))
    monkeypatch.setattr(system_info, "cfg_filename", cfg_filename)
    monkeypatch.setattr(system_info, "cfg_content", system_info._get_cfg_content())

    assert system_info._get_swap_pkgs() == expected

    if message:
        assert message in caplog.text
    else:
        assert "" == caplog.text
