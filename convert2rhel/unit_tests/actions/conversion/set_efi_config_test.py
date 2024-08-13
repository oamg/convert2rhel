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
import shutil

import pytest
import six

from convert2rhel import actions, grub, systeminfo, unit_tests
from convert2rhel.actions.conversion import set_efi_config
from convert2rhel.unit_tests.conftest import centos7


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def new_default_efi_bin_instance():
    return set_efi_config.NewDefaultEfiBin()


@pytest.fixture
def efi_bootmgr_utility_installed_instance():
    return set_efi_config.EfibootmgrUtilityInstalled()


@pytest.fixture
def move_grub_files_instance():
    return set_efi_config.MoveGrubFiles()


@pytest.fixture
def remove_efi_centos_instance():
    return set_efi_config.RemoveEfiCentos()


@pytest.fixture
def replace_efi_boot_entry_instance():
    return set_efi_config.ReplaceEfiBootEntry()


@pytest.mark.parametrize(
    ("is_efi", "efi_file_exists", "log_msg"),
    (
        (False, None, "BIOS detected"),
        (True, True, "UEFI binary found"),
    ),
)
def test_new_default_efi_bin(new_default_efi_bin_instance, is_efi, efi_file_exists, log_msg, monkeypatch, caplog):
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=efi_file_exists))
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=is_efi))
    new_default_efi_bin_instance.run()
    assert log_msg in caplog.records[-1].message
    unit_tests.assert_actions_result(
        new_default_efi_bin_instance,
        level="SUCCESS",
    )


def test_new_default_efi_bin_error(new_default_efi_bin_instance, monkeypatch):
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=False))
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=True))
    new_default_efi_bin_instance.run()
    unit_tests.assert_actions_result(
        new_default_efi_bin_instance,
        level="ERROR",
        id="NOT_FOUND_RHEL_UEFI_BINARIES",
        title="RHEL UEFI binaries not found",
        description="None of the expected RHEL UEFI binaries exist.",
        diagnosis="Bootloader couldn't be migrated due to missing RHEL EFI binaries: /boot/efi/EFI/redhat/shimx64.efi, /boot/efi/EFI/redhat/grubx64.efi .",
        remediations="Verify the bootloader configuration as follows and reboot the system. Ensure that `grubenv` and `grub.cfg` files are present in the /boot/efi/EFI/redhat/ directory. Verify that `efibootmgr -v` shows a bootloader entry for Red Hat Enterprise Linux that points to to '\\EFI\\redhat\\shimx64.efi'.",
    )


def test_efi_bootmgr_utility_installed_error(efi_bootmgr_utility_installed_instance, monkeypatch):
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=False))
    efi_bootmgr_utility_installed_instance.run()

    unit_tests.assert_actions_result(
        efi_bootmgr_utility_installed_instance,
        level="ERROR",
        id="NOT_INSTALLED_EFIBOOTMGR_UTILITY",
        title="UEFI boot manager utility not found",
        description="Couldn't find the UEFI boot manager which is required for us to install and verify a RHEL boot entry.",
        remediations="Install the efibootmgr utility using the following command:\n\n 1. yum install efibootmgr",
    )


@pytest.mark.parametrize(
    ("available_files",),
    (
        (
            [
                "grubenv",
                "grub.cfg",
                "user.cfg",
            ],
        ),
        (
            [
                "grubenv",
                "user.cfg",
            ],
        ),
        (
            [
                "grubenv",
            ],
        ),
        # This is not a required file
        (
            [
                "user.cfg",
            ],
        ),
    ),
)
def test_move_grub_files(
    available_files,
    monkeypatch,
    move_grub_files_instance,
    global_system_info,
    tmpdir,
):
    global_system_info.id = "centos"
    monkeypatch.setattr(systeminfo, "system_info", global_system_info)
    centos_efidir = tmpdir.join("centos").mkdir()
    # Create an empty file at the centos_efidir/{file} location
    [centos_efidir.join(file).write("\n") for file in available_files]
    monkeypatch.setattr(set_efi_config, "CENTOS_EFIDIR_CANONICAL_PATH", str(centos_efidir))
    rhel_efidir = tmpdir.join("rhel").mkdir()
    monkeypatch.setattr(set_efi_config, "RHEL_EFIDIR_CANONICAL_PATH", str(rhel_efidir))

    move_grub_files_instance.run()

    for file in available_files:
        assert os.path.join(str(rhel_efidir), file)


def test_move_grub_files_non_centos(monkeypatch, move_grub_files_instance, caplog, global_system_info):
    global_system_info.id = "oracle"
    monkeypatch.setattr(systeminfo, "system_info", global_system_info)
    move_grub_files_instance.run()
    assert "Did not perform moving of GRUB files" in caplog.text


def test_move_grub_files_error(monkeypatch, caplog, move_grub_files_instance, global_system_info):
    monkeypatch.setattr(os.path, "exists", lambda file: False)
    monkeypatch.setattr(shutil, "move", mock.Mock())
    global_system_info.id = "centos"
    monkeypatch.setattr(systeminfo, "system_info", global_system_info)

    move_grub_files_instance.run()
    unit_tests.assert_actions_result(
        move_grub_files_instance,
        level="ERROR",
        id="UNABLE_TO_FIND_REQUIRED_FILE_FOR_GRUB_CONFIG",
        title="Couldn't find system GRUB config",
        description="Couldn't find one of the GRUB config files in the current system which is required for configuring UEFI for RHEL: /boot/efi/EFI/centos/grubenv, /boot/efi/EFI/centos/grub.cfg",
    )


@centos7
def test_move_grub_files_io_error(
    monkeypatch,
    caplog,
    pretend_os,
    move_grub_files_instance,
):
    monkeypatch.setattr(shutil, "move", mock.Mock())
    shutil.move.side_effect = IOError(13, "Permission denied")
    monkeypatch.setattr(os.path, "exists", mock.Mock(side_effect=[False, True, True, True, False, True, False]))
    move_grub_files_instance.run()

    unit_tests.assert_actions_result(
        move_grub_files_instance,
        level="ERROR",
        id="GRUB_FILES_NOT_MOVED_TO_BOOT_DIRECTORY",
        title="GRUB files have not been moved to boot directory",
        description=(
            "I/O error(13): 'Permission denied'. Some GRUB files have not been moved to /boot/efi/EFI/redhat."
        ),
    )


def test_remove_efi_centos_warning(monkeypatch, remove_efi_centos_instance):

    monkeypatch.setattr(os, "rmdir", mock.Mock())
    os.rmdir.side_effect = OSError("Could not remove folder")
    remove_efi_centos_instance.run()

    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="NOT_REMOVED_CENTOS_UEFI_DIRECTORY",
                title="CentOS UEFI directory couldn't be removed",
                description="Failed to remove the /boot/efi/EFI/centos/ directory as files still exist. During conversion we make sure to move over files needed to their RHEL counterpart. However, some files we didn't expect likely exist in the directory that needs human oversight. Make sure that the files within the directory is taken care of and proceed with deleting the directory manually after conversion. We received error: 'Could not remove folder'.",
            ),
        )
    )
    assert expected.issuperset(remove_efi_centos_instance.messages)
    assert expected.issubset(remove_efi_centos_instance.messages)


def test_remove_efi_centos_non_centos(monkeypatch, remove_efi_centos_instance, global_system_info, caplog):
    global_system_info.id = "oracle"
    monkeypatch.setattr(systeminfo, "system_info", global_system_info)
    remove_efi_centos_instance.run()
    assert "Did not perform removal of EFI files" in caplog.text
    assert "Failed to remove the folder" not in caplog.text


def test_replace_efi_boot_entry_error(monkeypatch, replace_efi_boot_entry_instance):

    monkeypatch.setattr(grub, "replace_efi_boot_entry", mock.Mock(side_effect=grub.BootloaderError("Bootloader error")))
    replace_efi_boot_entry_instance.run()
    unit_tests.assert_actions_result(
        replace_efi_boot_entry_instance,
        level="ERROR",
        id="FAILED_TO_REPLACE_UEFI_BOOT_ENTRY",
        title="Failed to replace UEFI boot entry to RHEL",
        description="As the current UEFI bootloader entry could be invalid or missing we need to ensure that a RHEL UEFI entry exists. The UEFI boot entry could not be replaced due to the following error: 'Bootloader error'",
    )
