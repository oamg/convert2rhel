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
def copy_grub_files_instance():
    return set_efi_config.CopyGrubFiles()


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
        id="RHEL_UEFI_BINARIES_DO_NOT_EXIST",
        title="RHEL UEFI binaries do not exist",
        description="None of the expected RHEL UEFI binaries exist.",
        diagnosis="The migration of the bootloader setup was not successful.",
        remediations=(
            "Do not reboot your machine before doing a manual check of the\n"
            "bootloader configuration. Ensure that grubenv and grub.cfg files\n"
            "are present in the %s directory and that\n"
            "a new bootloader entry for Red Hat Enterprise Linux exists\n"
            "(check `efibootmgr -v` output).\n"
            "The entry should point to '\\EFI\\redhat\\shimx64.efi'." % grub.RHEL_EFIDIR_CANONICAL_PATH
        ),
    )


def test_efi_bootmgr_utility_installed_error(efi_bootmgr_utility_installed_instance, monkeypatch):
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=False))
    efi_bootmgr_utility_installed_instance.run()

    unit_tests.assert_actions_result(
        efi_bootmgr_utility_installed_instance,
        level="ERROR",
        id="EFIBOOTMGR_UTILITY_NOT_INSTALLED",
        title="Efibootmgr utility is not installed",
        description="The /usr/sbin/efibootmgr utility is not installed.",
        remediations="Install the efibootmgr utility via YUM/DNF.",
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
def test_copy_grub_files(
    available_files,
    monkeypatch,
    copy_grub_files_instance,
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

    copy_grub_files_instance.run()

    for file in available_files:
        assert os.path.join(str(rhel_efidir), file)


def test_copy_grub_files_non_centos(monkeypatch, copy_grub_files_instance, caplog, global_system_info):
    global_system_info.id = "oracle"
    monkeypatch.setattr(systeminfo, "system_info", global_system_info)
    copy_grub_files_instance.run()
    assert "Did not perform copying of GRUB files" in caplog.text


def test_copy_grub_files_error(monkeypatch, caplog, copy_grub_files_instance, global_system_info):
    monkeypatch.setattr(os.path, "exists", lambda file: False)
    monkeypatch.setattr(shutil, "copy2", mock.Mock())
    global_system_info.id = "centos"
    monkeypatch.setattr(systeminfo, "system_info", global_system_info)

    copy_grub_files_instance.run()
    unit_tests.assert_actions_result(
        copy_grub_files_instance,
        level="ERROR",
        id="UNABLE_TO_FIND_REQUIRED_FILE_FOR_GRUB_CONFIG",
        title="Unable to find required file for GRUB config",
        description="Unable to find the original file required for GRUB configuration at: /boot/efi/EFI/centos/grubenv, /boot/efi/EFI/centos/grub.cfg",
    )


@centos7
def test_copy_grub_files_io_error(
    monkeypatch,
    caplog,
    pretend_os,
    copy_grub_files_instance,
):
    monkeypatch.setattr(shutil, "copy2", mock.Mock())
    shutil.copy2.side_effect = IOError(13, "Permission denied")
    monkeypatch.setattr(os.path, "exists", mock.Mock(side_effect=[False, True, True, True, False, True]))
    copy_grub_files_instance.run()

    unit_tests.assert_actions_result(
        copy_grub_files_instance,
        level="ERROR",
        id="GRUB_FILES_NOT_COPIED_TO_BOOT_DIRECTORY",
        title="GRUB files have not been copied to boot directory",
        description=("I/O error(13): Permission denied Some GRUB files have not been copied to /boot/efi/EFI/redhat."),
    )


def test_remove_efi_centos_warning(monkeypatch, remove_efi_centos_instance):

    monkeypatch.setattr(os, "rmdir", mock.Mock())
    os.rmdir.side_effect = OSError()
    remove_efi_centos_instance.run()

    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="CENTOS_EFI_DIRECTORY_NOT_REMOVED",
                title="Centos EFI directory was not removed",
                description="The folder %s is left untouched. You may remove the folder manually"
                " after you ensure there is no custom data you would need." % grub.CENTOS_EFIDIR_CANONICAL_PATH,
            ),
        )
    )
    assert expected.issuperset(remove_efi_centos_instance.messages)
    assert expected.issubset(remove_efi_centos_instance.messages)


def test_replace_efi_boot_entry_error(monkeypatch, replace_efi_boot_entry_instance):

    monkeypatch.setattr(grub, "replace_efi_boot_entry", mock.Mock(side_effect=grub.BootloaderError("Bootloader error")))
    replace_efi_boot_entry_instance.run()
    unit_tests.assert_actions_result(
        replace_efi_boot_entry_instance,
        level="ERROR",
        id="FAILED_TO_REPLACE_EFI_BOOT_ENTRY",
        title="Failed to replace EFI boot entry",
        description="Bootloader error",
    )
