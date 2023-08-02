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

import unittest

import six

from convert2rhel import actions, unit_tests
from convert2rhel.actions.system_checks import readonly_mounts
from convert2rhel.unit_tests import GetFileContentMocked, GetLoggerMocked


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


class TestReadOnlyMountsChecks(unittest.TestCase):
    def setUp(self):
        self.readonly_mounts_action_mnt = readonly_mounts.ReadonlyMountMnt()
        self.readonly_mounts_action_sys = readonly_mounts.ReadonlyMountSys()

    @unit_tests.mock(readonly_mounts, "logger", GetLoggerMocked())
    @unit_tests.mock(
        readonly_mounts,
        "get_file_content",
        GetFileContentMocked(
            data=[
                "sysfs /sys sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "mnt /mnt sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
            ]
        ),
    )
    def test_mounted_mnt_is_readwrite(self):
        self.readonly_mounts_action_mnt.run()
        self.assertEqual(len(readonly_mounts.logger.debug_msgs), 1)
        self.assertIn("/mnt mount point is not read-only.", readonly_mounts.logger.debug_msgs)

    @unit_tests.mock(readonly_mounts, "logger", GetLoggerMocked())
    @unit_tests.mock(
        readonly_mounts,
        "get_file_content",
        GetFileContentMocked(
            data=[
                "sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "mnt /mnt sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
            ]
        ),
    )
    def test_mounted_sys_is_readwrite(self):
        self.readonly_mounts_action_sys.run()
        self.assertEqual(len(readonly_mounts.logger.debug_msgs), 1)
        self.assertIn("/sys mount point is not read-only.", readonly_mounts.logger.debug_msgs)

    @unit_tests.mock(readonly_mounts, "logger", GetLoggerMocked())
    @unit_tests.mock(
        readonly_mounts,
        "get_file_content",
        GetFileContentMocked(
            data=[
                "sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "mnt /mnt sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
            ]
        ),
    )
    def test_mounted_are_readonly_mnt(self):
        self.readonly_mounts_action_mnt.run()
        self.assertEqual(self.readonly_mounts_action_mnt.result.level, actions.STATUS_CODE["ERROR"])
        self.assertEqual(self.readonly_mounts_action_mnt.result.id, "MNT_DIR_READONLY_MOUNT")
        self.assertEqual(
            self.readonly_mounts_action_mnt.result.message,
            (
                "Stopping conversion due to read-only mount to /mnt directory.\n"
                "Mount at a subdirectory of /mnt to have /mnt writeable."
            ),
        )

    @unit_tests.mock(readonly_mounts, "logger", GetLoggerMocked())
    @unit_tests.mock(
        readonly_mounts,
        "get_file_content",
        GetFileContentMocked(
            data=[
                "mnt /mnt sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "sysfs /sys sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
            ]
        ),
    )
    def test_mounted_are_readonly_sys(self):
        self.readonly_mounts_action_sys.run()
        self.assertEqual(self.readonly_mounts_action_sys.result.level, actions.STATUS_CODE["ERROR"])
        self.assertEqual(self.readonly_mounts_action_sys.result.id, "SYS_DIR_READONLY_MOUNT")
        self.assertEqual(
            self.readonly_mounts_action_sys.result.message,
            (
                "Stopping conversion due to read-only mount to /sys directory.\n"
                "Ensure mount point is writable before executing convert2rhel."
            ),
        )
