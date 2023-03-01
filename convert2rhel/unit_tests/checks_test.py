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

import pytest
import six

from convert2rhel import checks
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    ("latest_installed_kernel", "subprocess_output", "expected"),
    (
        ("6.1.7-200.fc37.x86_64", ("test", 0), True),
        ("6.1.7-200.fc37.x86_64", ("error", 1), False),
    ),
)
def test_is_initramfs_file_valid(latest_installed_kernel, subprocess_output, expected, tmpdir, caplog, monkeypatch):
    initramfs_file = tmpdir.mkdir("/boot").join("initramfs-%s.img")
    initramfs_file = str(initramfs_file)
    initramfs_file = initramfs_file % latest_installed_kernel
    with open(initramfs_file, mode="w") as _:
        pass

    monkeypatch.setattr(checks, "INITRAMFS_FILEPATH", initramfs_file)
    monkeypatch.setattr(checks, "run_subprocess", mock.Mock(return_value=subprocess_output))
    result = checks._is_initramfs_file_valid(initramfs_file)
    assert result == expected

    if not expected:
        assert "Couldn't verify initramfs file. It may be corrupted." in caplog.records[-2].message
        assert "Output of lsinitrd: %s" % subprocess_output[0] in caplog.records[-1].message


@centos8
def test_check_kernel_boot_files(pretend_os, tmpdir, caplog, monkeypatch):
    rpm_last_kernel_output = ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0)
    latest_installed_kernel = "6.1.8-200.fc37.x86_64"

    boot_folder = tmpdir.mkdir("/boot")
    initramfs_file = boot_folder.join("initramfs-%s.img")
    vmlinuz_file = boot_folder.join("vmlinuz-%s")
    initramfs_file = str(initramfs_file)
    vmlinuz_file = str(vmlinuz_file)

    with open(initramfs_file % latest_installed_kernel, mode="w") as _:
        pass

    with open(vmlinuz_file % latest_installed_kernel, mode="w") as _:
        pass

    monkeypatch.setattr(checks, "VMLINUZ_FILEPATH", vmlinuz_file)
    monkeypatch.setattr(checks, "INITRAMFS_FILEPATH", initramfs_file)
    monkeypatch.setattr(checks, "run_subprocess", mock.Mock(side_effect=[rpm_last_kernel_output, ("test", 0)]))

    checks.check_kernel_boot_files()
    assert "The initramfs and vmlinuz files are valid." in caplog.records[-1].message


@pytest.mark.parametrize(
    ("create_initramfs", "create_vmlinuz", "run_piped_subprocess", "rpm_last_kernel_output", "latest_installed_kernel"),
    (
        pytest.param(
            False,
            False,
            ("", 0),
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="both-files-missing",
        ),
        pytest.param(
            True,
            False,
            ("test", 0),
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="vmlinuz-missing",
        ),
        pytest.param(
            False,
            True,
            ("test", 0),
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="initramfs-missing",
        ),
        pytest.param(
            True,
            True,
            ("error", 1),
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="initramfs-corrupted",
        ),
    ),
)
@centos8
def test_check_kernel_boot_files_missing(
    pretend_os,
    create_initramfs,
    create_vmlinuz,
    run_piped_subprocess,
    rpm_last_kernel_output,
    latest_installed_kernel,
    tmpdir,
    caplog,
    monkeypatch,
):
    """
    This test will check if we output the warning message correctly if either
    initramfs or vmlinuz are missing.
    """
    # We are mocking both subprocess calls here in order to make it easier for
    # testing any type of parametrization we may include in the future. Note
    # that the second iteration may not run sometimes, as this is specific for
    # when we want to check if a file is corrupted or not.
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        mock.Mock(
            side_effect=[
                rpm_last_kernel_output,
                run_piped_subprocess,
            ]
        ),
    )
    boot_folder = tmpdir.mkdir("/boot")
    if create_initramfs:
        initramfs_file = boot_folder.join("initramfs-%s.img")
        initramfs_file = str(initramfs_file)
        with open(initramfs_file % latest_installed_kernel, mode="w") as _:
            pass

        monkeypatch.setattr(checks, "INITRAMFS_FILEPATH", initramfs_file)
    else:
        monkeypatch.setattr(checks, "INITRAMFS_FILEPATH", "/non-existing-%s.img")

    if create_vmlinuz:
        vmlinuz_file = boot_folder.join("vmlinuz-%s")
        vmlinuz_file = str(vmlinuz_file)
        with open(vmlinuz_file % latest_installed_kernel, mode="w") as _:
            pass

        monkeypatch.setattr(checks, "VMLINUZ_FILEPATH", vmlinuz_file)
    else:
        monkeypatch.setattr(checks, "VMLINUZ_FILEPATH", "/non-existing-%s")

    checks.check_kernel_boot_files()
    assert "Couldn't verify the kernel boot files in the boot partition." in caplog.records[-1].message
