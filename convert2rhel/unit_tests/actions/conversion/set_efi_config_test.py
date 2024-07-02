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

from convert2rhel import actions, grub, unit_tests
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
    ("sys_id", "src_file_exists", "dst_file_exists", "log_msg"),
    (
        ("oracle", None, None, "only related to CentOS Linux"),
        ("centos", None, True, "file already exists"),
        ("centos", True, False, "Copying '"),
    ),
)
def test__copy_grub_files(
    sys_id,
    src_file_exists,
    dst_file_exists,
    log_msg,
    monkeypatch,
    caplog,
    copy_grub_files_instance,
    global_system_info,
):
    def path_exists(path):
        return src_file_exists if grub.CENTOS_EFIDIR_CANONICAL_PATH in path else dst_file_exists

    monkeypatch.setattr(os.path, "exists", mock.Mock(side_effect=path_exists))
    monkeypatch.setattr(shutil, "copy2", mock.Mock())
    global_system_info.id = sys_id

    copy_grub_files_instance.run()
    assert any(log_msg in record.message for record in caplog.records)
    if sys_id == "centos" and src_file_exists and not dst_file_exists:
        assert shutil.copy2.call_args_list == [
            mock.call("/boot/efi/EFI/centos/grubenv", "/boot/efi/EFI/redhat/grubenv"),
            mock.call("/boot/efi/EFI/centos/grub.cfg", "/boot/efi/EFI/redhat/grub.cfg"),
            mock.call("/boot/efi/EFI/centos/user.cfg", "/boot/efi/EFI/redhat/user.cfg"),
        ]


@pytest.mark.parametrize(
    ("sys_id", "src_file_exists", "dst_file_exists"),
    (("centos", False, False),),
)
def test__copy_grub_files_error(
    sys_id, src_file_exists, dst_file_exists, monkeypatch, caplog, copy_grub_files_instance, global_system_info
):
    def path_exists(path):
        return src_file_exists if grub.CENTOS_EFIDIR_CANONICAL_PATH in path else dst_file_exists

    monkeypatch.setattr(os.path, "exists", path_exists)
    monkeypatch.setattr(shutil, "copy2", mock.Mock())
    global_system_info.id = sys_id

    copy_grub_files_instance.run()
    unit_tests.assert_actions_result(
        copy_grub_files_instance,
        level="ERROR",
        id="UNABLE_TO_FIND_REQUIRED_FILE_FOR_GRUB_CONFIG",
        title="Unable to find required file for GRUB config",
        description="Unable to find the original file required for GRUB configuration: /boot/efi/EFI/centos/grubenv",
    )


@centos7
@pytest.mark.parametrize(
    ("sys_id", "src_file_exists", "dst_file_exists"),
    (("centos", False, False),),
)
def test__copy_grub_files_io_error(
    monkeypatch,
    caplog,
    sys_id,
    src_file_exists,
    dst_file_exists,
    pretend_os,
    copy_grub_files_instance,
):

    monkeypatch.setattr(shutil, "copy2", mock.Mock())
    shutil.copy2.side_effect = IOError(13, "Permission denied")
    monkeypatch.setattr(os.path, "exists", mock.Mock(side_effect=[False, True, True, True]))
    copy_grub_files_instance.run()
    unit_tests.assert_actions_result(
        copy_grub_files_instance,
        level="ERROR",
        id="IO_ERROR",
        title="I/O error",
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
                id="FOLDER_NOT_REMOVED",
                title="Folder was not removed",
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
        id="BOOTLOADER_ERROR",
        title="Bootloader error",
        description="Bootloader error",
    )
