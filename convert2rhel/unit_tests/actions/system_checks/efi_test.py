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

import os

from collections import namedtuple

import pytest

from six.moves import mock

from convert2rhel import actions, systeminfo, unit_tests
from convert2rhel.actions.system_checks import efi
from convert2rhel.bootloader import bootloader, grub
from convert2rhel.unit_tests import EFIBootInfoMocked


ExpectedMessage = namedtuple("ExpectedMessage", ("id", "title", "description", "diagnosis", "remediations", "log_msg"))


@pytest.fixture
def efi_action():
    return efi.Efi()


class TestEFIChecks:
    @pytest.mark.parametrize(
        ("is_efi", "is_secure_boot", "arch", "version", "os_path_exists", "boot_info", "expected"),
        (
            (
                True,
                False,
                "x86_64",
                systeminfo.Version(7, 9),
                lambda x: not x == "/usr/sbin/efibootmgr",
                EFIBootInfoMocked(exception=bootloader.BootloaderError("errmsg")),
                ExpectedMessage(
                    id="EFIBOOTMGR_NOT_FOUND",
                    title="EFI boot manager not found",
                    description="The EFI boot manager could not be found.",
                    diagnosis="The EFI boot manager tool - efibootmgr could not be found on your system",
                    remediations="Install efibootmgr to continue converting the UEFI-based system.",
                    log_msg="UEFI detected",
                ),
            ),
            (
                True,
                False,
                "aarch64",
                systeminfo.Version(7, 9),
                lambda x: not x == "/usr/sbin/efibootmgr",
                EFIBootInfoMocked(exception=bootloader.BootloaderError("errmsg")),
                ExpectedMessage(
                    id="NON_x86_64",
                    title="None x86_64 system detected",
                    description="Only x86_64 systems are supported for UEFI conversions.",
                    diagnosis="",
                    remediations="",
                    log_msg="",
                ),
            ),
            (
                True,
                True,
                "x86_64",
                systeminfo.Version(7, 9),
                lambda x: x == "/usr/sbin/efibootmgr",
                EFIBootInfoMocked(exception=bootloader.BootloaderError("errmsg")),
                ExpectedMessage(
                    id="SECURE_BOOT_DETECTED",
                    title="Secure boot detected",
                    description="Secure boot has been detected.",
                    diagnosis="The conversion with secure boot is currently not possible.",
                    remediations="To disable secure boot, follow the instructions available in this article: https://access.redhat.com/solutions/6753681",
                    log_msg="Secure boot detected.",
                ),
            ),
            (
                True,
                False,
                "x86_64",
                systeminfo.Version(7, 9),
                lambda x: x == "/usr/sbin/efibootmgr",
                EFIBootInfoMocked(exception=bootloader.BootloaderError("errmsg")),
                ExpectedMessage(
                    id="BOOTLOADER_ERROR",
                    title="Bootloader error detected",
                    description="An unknown bootloader error occurred, please look at the diagnosis for more information.",
                    diagnosis="errmsg",
                    remediations="",
                    log_msg="",
                ),
            ),
        ),
        ids=(
            "EFI detected without efibootmgr",
            "EFI detected non-Intel",
            "EFI detected secure boot",
            "EFI detected bootloader error",
        ),
    )
    def test_check_efi_errors(
        self,
        is_efi,
        is_secure_boot,
        arch,
        version,
        os_path_exists,
        boot_info,
        expected,
        efi_action,
        caplog,
        monkeypatch,
    ):
        monkeypatch.setattr(bootloader, "is_efi", lambda: is_efi)
        monkeypatch.setattr(bootloader, "is_secure_boot", lambda: is_secure_boot)
        monkeypatch.setattr(efi.system_info, "arch", arch)
        monkeypatch.setattr(efi.system_info, "version", version)
        monkeypatch.setattr(os.path, "exists", os_path_exists)
        monkeypatch.setattr(bootloader, "EFIBootInfo", boot_info)

        efi_action.run()

        unit_tests.assert_actions_result(
            efi_action,
            level="ERROR",
            id=expected.id,
            title=expected.title,
            description=expected.description,
            diagnosis=expected.diagnosis,
            remediations=expected.remediations,
        )
        assert expected.log_msg in caplog.text

    def test_check_efi_efi_detected_nofile_entry(self, efi_action, caplog, monkeypatch):
        monkeypatch.setattr(bootloader, "is_efi", lambda: True)
        monkeypatch.setattr(bootloader, "is_secure_boot", lambda: False)
        monkeypatch.setattr(efi.system_info, "arch", "x86_64")
        monkeypatch.setattr(efi.system_info, "version", systeminfo.Version(7, 9))
        monkeypatch.setattr(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
        monkeypatch.setattr(bootloader, "EFIBootInfo", EFIBootInfoMocked(current_bootnum="0002"))
        monkeypatch.setattr(bootloader, "get_device_number", mock.Mock(return_value=1))
        monkeypatch.setattr(grub, "get_efi_partition", mock.Mock(return_value="/dev/sda"))

        efi_action.run()

        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="UEFI_BOOTLOADER_MISMATCH",
                    title="UEFI bootloader mismatch",
                    description="There was a UEFI bootloader mismatch.",
                    diagnosis=(
                        "The current UEFI bootloader '0002' is not referring to any binary UEFI"
                        " file located on local EFI System Partition (ESP)."
                    ),
                    remediations="",
                ),
            )
        )
        assert expected.issuperset(efi_action.messages)
        assert expected.issubset(efi_action.messages)

        log_msg = "UEFI detected."
        warn_msg = (
            "The current UEFI bootloader '0002' is not referring to any binary UEFI file located on local"
            " EFI System Partition (ESP)."
        )

        assert log_msg in caplog.text
        assert warn_msg in caplog.text

    def test_check_efi_efi_detected_ok(self, efi_action, caplog, monkeypatch):
        monkeypatch.setattr(bootloader, "is_efi", lambda: True)
        monkeypatch.setattr(bootloader, "is_secure_boot", lambda: False)
        monkeypatch.setattr(efi.system_info, "arch", "x86_64")
        monkeypatch.setattr(efi.system_info, "version", systeminfo.Version(7, 9))
        monkeypatch.setattr(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
        monkeypatch.setattr(bootloader, "EFIBootInfo", EFIBootInfoMocked())

        efi_action.run()

        assert "UEFI detected." in caplog.text
        assert not [log_msg for log_msg in caplog.records if log_msg.levelname in ("WARNING", "ERROR", "CRITICAL")]
