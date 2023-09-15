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

import six

from convert2rhel import unit_tests
from convert2rhel.actions.system_checks import readonly_mounts


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
import pytest

from six.moves import mock


@pytest.fixture
def readonly_mounts_mnt():
    return readonly_mounts.ReadonlyMountMnt()


@pytest.fixture
def readonly_mounts_sys():
    return readonly_mounts.ReadonlyMountSys()


class TestReadOnlyMountsChecks:
    def test_mounted_mnt_is_readwrite(self, readonly_mounts_mnt, caplog, monkeypatch):
        monkeypatch.setattr(
            readonly_mounts,
            "get_file_content",
            mock.Mock(
                return_value=[
                    "sysfs /sys sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "mnt /mnt sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
                ]
            ),
        )
        readonly_mounts_mnt.run()

        unit_tests.assert_actions_result(
            readonly_mounts_mnt,
            level="SUCCESS",
        )
        assert "Read-only /mnt mount point not detected." in caplog.text

    def test_mounted_sys_is_readwrite(self, readonly_mounts_sys, caplog, monkeypatch):
        monkeypatch.setattr(
            readonly_mounts,
            "get_file_content",
            mock.Mock(
                return_value=[
                    "sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "mnt /mnt sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
                ]
            ),
        )
        readonly_mounts_sys.run()

        unit_tests.assert_actions_result(
            readonly_mounts_sys,
            level="SUCCESS",
        )
        assert "Read-only /sys mount point not detected." in caplog.text

    def test_mounted_are_readonly_mnt(self, readonly_mounts_mnt, monkeypatch):
        monkeypatch.setattr(
            readonly_mounts,
            "get_file_content",
            mock.Mock(
                return_value=[
                    "sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "mnt /mnt sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
                ]
            ),
        )

        readonly_mounts_mnt.run()

        unit_tests.assert_actions_result(
            readonly_mounts_mnt,
            level="ERROR",
            id="MNT_DIR_READONLY_MOUNT",
            title="Read-only mount in /mnt directory",
            description=(
                "Stopping conversion due to read-only mount to /mnt directory.\n"
                "Mount at a subdirectory of /mnt to have /mnt writeable."
            ),
            diagnosis="",
            remediation="",
        )

    def test_mounted_are_readonly_sys(self, readonly_mounts_sys, monkeypatch):
        monkeypatch.setattr(
            readonly_mounts,
            "get_file_content",
            mock.Mock(
                return_value=[
                    "mnt /mnt sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "sysfs /sys sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                    "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
                ]
            ),
        )

        readonly_mounts_sys.run()

        unit_tests.assert_actions_result(
            readonly_mounts_sys,
            level="ERROR",
            id="SYS_DIR_READONLY_MOUNT",
            title="Read-only mount in /sys directory",
            description=(
                "Stopping conversion due to read-only mount to /sys directory.\n"
                "Ensure mount point is writable before executing convert2rhel."
            ),
            diagnosis=None,
            remediation=None,
        )
