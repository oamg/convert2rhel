# Copyright(C) 2024 Red Hat, Inc.
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

import pytest
import six

from convert2rhel import actions, checks, grub
from convert2rhel.actions.post_conversion import kernel_boot_files
from convert2rhel.unit_tests import RunSubprocessMocked
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def kernel_boot_files_instance():
    return kernel_boot_files.KernelBootFiles()


@centos8
def test_check_kernel_boot_files(pretend_os, tmpdir, caplog, monkeypatch, kernel_boot_files_instance):
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
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=True))
    monkeypatch.setattr(checks, "is_initramfs_file_valid", mock.Mock(return_value=True))
    monkeypatch.setattr(
        checks, "run_subprocess", RunSubprocessMocked(side_effect=[rpm_last_kernel_output, ("test", 0)])
    )

    kernel_boot_files_instance.run()
    assert "The initramfs and vmlinuz files are valid." in caplog.records[-1].message


@pytest.mark.parametrize(
    ("vmlinuz_exists", "initiramfs_exists", "rpm_last_kernel_output", "latest_installed_kernel"),
    (
        pytest.param(
            False,
            True,
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="vmlinuz-missing",
        ),
        pytest.param(
            True,
            False,
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="vmlinuz-missing",
        ),
        pytest.param(
            False,
            False,
            ("kernel-core-6.1.8-200.fc37.x86_64 Wed 01 Feb 2023 14:01:01 -03", 0),
            "6.1.8-200.fc37.x86_64",
            id="vmlinuz-missing",
        ),
    ),
)
@centos8
def test_check_kernel_boot_files_missing(
    pretend_os,
    vmlinuz_exists,
    initiramfs_exists,
    rpm_last_kernel_output,
    latest_installed_kernel,
    caplog,
    monkeypatch,
    kernel_boot_files_instance,
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
        kernel_boot_files,
        "run_subprocess",
        mock.Mock(side_effect=[rpm_last_kernel_output]),
    )

    # We are always expecting that the grub config file is pointed to /boot/grub2/grub.cfg. We can change this in the
    # future, but for this test is fine if the path is always the same.
    monkeypatch.setattr(grub, "get_grub_config_file", lambda: "/boot/grub2/grub.cfg")
    monkeypatch.setattr(checks, "is_initramfs_file_valid", lambda x: initiramfs_exists)
    monkeypatch.setattr(os.path, "exists", lambda x: vmlinuz_exists)

    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="UNABLE_TO_VERIFY_KERNEL_BOOT_FILES",
                title="Unable to verify kernel boot files and boot partition",
                description="We failed to determine whether boot partition is configured correctly and that boot"
                " files exists. This may cause problems during the next boot of your system.",
                diagnosis=None,
                remediations=(
                    "In order to fix this problem you might need to free/increase space in your boot partition and then run the following commands in your terminal:\n"
                    "1. yum reinstall kernel-core-{} -y\n"
                    "2. grub2-mkconfig -o /boot/grub2/grub.cfg\n"
                    "3. reboot"
                ).format(latest_installed_kernel),
            ),
        )
    )

    kernel_boot_files_instance.run()
    assert "Couldn't verify the kernel boot files in the boot partition." in caplog.records[-1].message
    assert expected.issuperset(kernel_boot_files_instance.messages)
    assert expected.issubset(kernel_boot_files_instance.messages)
