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

# Required imports:
import logging
import os
import shutil
import socket
import sys
import time
import unittest

from collections import namedtuple

import pytest
import six

from convert2rhel import logger, systeminfo, unit_tests, utils  # Imports unit_tests/__init__.py
from convert2rhel.systeminfo import RELEASE_VER_MAPPING, system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import is_rpm_based_os
from convert2rhel.unit_tests.conftest import all_systems, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class TestSysteminfo(unittest.TestCase):
    class RunSubprocessMocked(unit_tests.MockFunction):
        def __init__(self, output_tuple=("output", 0)):
            self.output_tuple = output_tuple
            self.called = 0
            self.used_args = []

        def __call__(self, *args, **kwargs):
            self.called += 1
            self.used_args.append(args)
            return self.output_tuple

    class PathExistsMocked(unit_tests.MockFunction):
        def __init__(self, return_value=True):
            self.return_value = return_value

        def __call__(self, filepath):
            return self.return_value

    class GenerateRpmVaMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self):
            self.called += 1

    class GetLoggerMocked(unit_tests.MockFunction):
        def __init__(self):
            self.task_msgs = []
            self.info_msgs = []
            self.warning_msgs = []
            self.critical_msgs = []

        def __call__(self, msg):
            return self

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def task(self, msg):
            self.task_msgs.append(msg)

        def info(self, msg):
            self.info_msgs.append(msg)

        def warn(self, msg, *args):
            self.warning_msgs.append(msg)

        def warning(self, msg, *args):
            self.warn(msg, *args)

        def debug(self, msg):
            pass

    class GetFileContentMocked(unit_tests.MockFunction):
        def __init__(self, data):
            self.data = data
            self.as_list = True
            self.called = 0

        def __call__(self, filename, as_list):
            self.called += 1
            return self.data[self.called - 1]

    ##########################################################################

    def setUp(self):
        if os.path.exists(unit_tests.TMP_DIR):
            shutil.rmtree(unit_tests.TMP_DIR)
        os.makedirs(unit_tests.TMP_DIR)
        system_info.logger = logging.getLogger(__name__)

        self.rpmva_output_file = os.path.join(unit_tests.TMP_DIR, "rpm_va.log")

    def tearDown(self):
        if os.path.exists(unit_tests.TMP_DIR):
            shutil.rmtree(unit_tests.TMP_DIR)

    @unit_tests.mock(tool_opts, "no_rpm_va", True)
    def test_modified_rpm_files_diff_with_no_rpm_va(self):
        self.assertEqual(system_info.modified_rpm_files_diff(), None)

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(
        utils,
        "get_file_content",
        GetFileContentMocked(data=[["rpm1", "rpm2"], ["rpm1", "rpm2"]]),
    )
    def test_modified_rpm_files_diff_without_differences_after_conversion(
        self,
    ):
        self.assertEqual(system_info.modified_rpm_files_diff(), None)

    @unit_tests.mock(os.path, "exists", PathExistsMocked(True))
    @unit_tests.mock(tool_opts, "no_rpm_va", False)
    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(system_info, "logger", GetLoggerMocked())
    @unit_tests.mock(
        utils,
        "get_file_content",
        GetFileContentMocked(
            data=[
                [".M.......  g /etc/pki/ca-trust/extracted/java/cacerts"],
                [
                    ".M.......  g /etc/pki/ca-trust/extracted/java/cacerts",
                    "S.5....T.  c /etc/yum.conf",
                ],
            ]
        ),
    )
    @pytest.mark.skipif(
        not is_rpm_based_os(),
        reason="Current test runs only on rpm based systems.",
    )
    def test_modified_rpm_files_diff_with_differences_after_conversion(self):
        system_info.modified_rpm_files_diff()
        self.assertTrue(any("S.5....T.  c /etc/yum.conf" in elem for elem in system_info.logger.info_msgs))

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked(("rpmva\n", 0)))
    def test_generate_rpm_va(self):
        # TODO: move class from unittest to pytest and use global tool_opts fixture
        # Check that rpm -Va is executed (default) and stored into the specific file.
        tool_opts.no_rpm_va = False
        system_info.generate_rpm_va()
        self.assertTrue(utils.run_subprocess.called > 0)
        self.assertEqual(utils.run_subprocess.used_args[0][0], ["rpm", "-Va"])
        self.assertTrue(os.path.isfile(self.rpmva_output_file))
        self.assertEqual(utils.get_file_content(self.rpmva_output_file), "rpmva\n")

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(utils, "run_subprocess", RunSubprocessMocked())
    def test_generate_rpm_va_skip(self):
        # Check that rpm -Va is not called when the --no-rpm-va option is used.
        tool_opts.no_rpm_va = True
        system_info.generate_rpm_va()

        self.assertEqual(utils.run_subprocess.called, 0)
        self.assertFalse(os.path.exists(self.rpmva_output_file))

    def test_get_system_version(self):
        Version = namedtuple("Version", ["major", "minor"])
        versions = {
            "Oracle Linux Server release 6.10": Version(6, 10),
            "Oracle Linux Server release 7.8": Version(7, 8),
            "CentOS release 6.10 (Final)": Version(6, 10),
            "CentOS Linux release 7.6.1810 (Core)": Version(7, 6),
            "CentOS Linux release 8.1.1911 (Core)": Version(8, 1),
        }
        for system_release in versions:
            system_info.system_release_file_content = system_release
            version = system_info._get_system_version()
            self.assertEqual(version, versions[system_release])

        system_info.system_release_file_content = "not containing the release"
        self.assertRaises(SystemExit, system_info._get_system_version)


@pytest.mark.parametrize(
    ("pkg_name", "present_on_system", "expected_return"),
    [
        ("package A", True, True),
        ("package A", False, False),
        ("", None, False),
    ],
)
def test_system_info_has_rpm(pkg_name, present_on_system, expected_return, monkeypatch):
    run_subprocess_mocked = mock.Mock(return_value=("", 0) if present_on_system else ("", 1))
    monkeypatch.setattr(systeminfo, "run_subprocess", value=run_subprocess_mocked)
    assert system_info.is_rpm_installed(pkg_name) == expected_return
    assert run_subprocess_mocked


@all_systems
def test_get_release_ver(pretend_os):
    """Test if all pretended OSes presented in theh RELEASE_VER_MAPPING."""
    assert system_info.releasever in RELEASE_VER_MAPPING.values()


@pytest.mark.parametrize(
    (
        "releasever_val",
        "self_name",
        "self_version",
        "has_internet",
        "exception",
    ),
    (
        # good cases
        # if releasever set in config - it takes precedence
        ("not_existing_release_ver_set_in_config", None, None, True, None),
        # Good cases which matches supported pathes
        ("", "CentOS Linux", systeminfo.Version(8, 4), True, None),
        ("", "Oracle Linux Server", systeminfo.Version(8, 4), True, None),
        # bad cases
        ("", "NextCool Linux", systeminfo.Version(8, 4), False, SystemExit),
        ("", "CentOS Linux", systeminfo.Version(8, 10000), False, SystemExit),
    ),
)
# need to pretend centos8 in order to system info were resolved at module init
@centos8
def test_get_release_ver_other(
    pretend_os, monkeypatch, releasever_val, self_name, self_version, has_internet, exception
):
    monkeypatch.setattr(systeminfo.SystemInfo, "_get_cfg_opt", mock.Mock(return_value=releasever_val))
    monkeypatch.setattr(systeminfo.SystemInfo, "_check_internet_access", mock.Mock(return_value=has_internet))
    if self_name:
        monkeypatch.setattr(systeminfo.SystemInfo, "_get_system_name", mock.Mock(return_value=self_name))
    if self_version:
        monkeypatch.setattr(systeminfo.SystemInfo, "_get_system_version", mock.Mock(return_value=self_version))
    # calling resolve_system_info one more time to enable our monkeypatches
    if exception:
        with pytest.raises(exception):
            system_info.resolve_system_info()
    else:
        system_info.resolve_system_info()
    if releasever_val:
        assert system_info.releasever == releasever_val
    if has_internet:
        assert system_info.has_internet_access == has_internet


@pytest.mark.parametrize(
    ("side_effect", "expected"),
    (
        (None, True),
        (socket.error, False),
    ),
)
def test_check_internet_access(side_effect, expected, monkeypatch):
    monkeypatch.setattr(systeminfo.socket.socket, "connect", mock.Mock(side_effect=side_effect))
    # Have to initialize the logger since we are not constructing the
    # system_info object properly i.e: we are not calling `resolve_system_info()`
    system_info.logger = logging.getLogger(__name__)

    assert system_info._check_internet_access() == expected


@pytest.mark.parametrize(
    ("version_major", "command_output", "expected_command", "expected_output"),
    (
        (6, "messagebus: (pid  1315) is running...\n", ["/sbin/service", "messagebus", "status"], True),
        (6, "messagebus: unrecognized service\n", ["/sbin/service", "messagebus", "status"], False),
        (6, "", ["/sbin/service", "messagebus", "status"], False),
        (6, "master status unknown due to insufficient privileges.", ["/sbin/service", "messagebus", "status"], False),
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
    monkeypatch.setattr(system_info, "version", namedtuple("Version", ("major", "minor"))(version_major, 0))
    monkeypatch.setattr(time, "sleep", mock.Mock)
    run_subprocess_mocked = mock.Mock(return_value=(command_output, 0))
    monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

    assert system_info._is_dbus_running() == expected_output
    assert run_subprocess_mocked.called_once_with(expected_command)


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
    monkeypatch.setattr(system_info, "version", namedtuple("Version", ("major", "minor"))(8, 0))
    monkeypatch.setattr(time, "sleep", mock.Mock)

    side_effects = []
    for state in states:
        side_effects.append(("ActiveState=%s\n" % state, 0))

    run_subprocess_mocked = mock.Mock(side_effect=side_effects)
    monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)

    assert system_info._is_dbus_running() is expected


@pytest.mark.parametrize(
    ("releasever", "expected"),
    (
        ("7.9", False),
        ("8.4", True),
        ("8.5", False),
        ("8.6", False),
        ("8.7", False),
        ("8.8", False),
        ("8.9", False),
    ),
)
def test_corresponds_to_rhel_eus_release(releasever, expected):
    system_info.releasever = releasever
    assert system_info.corresponds_to_rhel_eus_release() == expected


@pytest.mark.parametrize(
    ("system_release_content", "expected"),
    (
        ("CentOS Linux release 8.1.1911 (Core)", "Core"),
        ("CentOS release 6.10 (Final)", "Final"),
        ("Oracle Linux Server release 7.8", None),
    ),
)
def test_get_system_distribution_id(system_release_content, expected):
    assert system_info._get_system_distribution_id(system_release_content) == expected


@centos8
def test_get_system_distribution_id_default_system_release_content(pretend_os):
    assert system_info._get_system_distribution_id() == None
