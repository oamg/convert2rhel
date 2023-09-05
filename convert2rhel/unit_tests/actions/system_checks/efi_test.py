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
import unittest

from collections import namedtuple

from convert2rhel import actions, grub, unit_tests
from convert2rhel.actions.system_checks import efi
from convert2rhel.unit_tests import EFIBootInfoMocked, GetLoggerMocked


def _gen_version(major, minor):
    return namedtuple("Version", ["major", "minor"])(major, minor)


class TestEFIChecks(unittest.TestCase):
    def setUp(self):
        self.efi_action = efi.Efi()

    def _check_efi_detection_log(self, efi_detected=True):
        if efi_detected:
            self.assertNotIn("BIOS detected.", efi.logger.info_msgs)
            self.assertIn("UEFI detected.", efi.logger.info_msgs)
        else:
            self.assertIn("BIOS detected.", efi.logger.info_msgs)
            self.assertNotIn("UEFI detected.", efi.logger.info_msgs)

    def _check_efi_critical(self, id, title, description, diagnosis, remediation):
        self.efi_action.run()
        self.assertEqual(self.efi_action.result.level, actions.STATUS_CODE["ERROR"])
        self.assertEqual(self.efi_action.result.id, id)
        self.assertEqual(self.efi_action.result.title, title)
        self.assertEqual(self.efi_action.result.description, description)
        self.assertEqual(self.efi_action.result.diagnosis, diagnosis)
        self.assertEqual(self.efi_action.result.remediation, remediation)
        self._check_efi_detection_log(True)

    @unit_tests.mock(grub, "is_efi", lambda: True)
    @unit_tests.mock(grub, "is_secure_boot", lambda: False)
    @unit_tests.mock(efi.system_info, "arch", "x86_64")
    @unit_tests.mock(efi.system_info, "version", _gen_version(7, 9))
    @unit_tests.mock(efi, "logger", GetLoggerMocked())
    @unit_tests.mock(os.path, "exists", lambda x: not x == "/usr/sbin/efibootmgr")
    @unit_tests.mock(
        grub,
        "EFIBootInfo",
        EFIBootInfoMocked(exception=grub.BootloaderError("errmsg")),
    )
    def test_check_efi_efi_detected_without_efibootmgr(self):
        self._check_efi_critical(
            "EFIBOOTMGR_NOT_FOUND",
            "EFI boot manager not found",
            "The EFI boot manager could not be found.",
            "The EFI boot manager tool - efibootmgr could not be found on your system",
            "Install efibootmgr to continue converting the UEFI-based system.",
        )

    @unit_tests.mock(grub, "is_efi", lambda: True)
    @unit_tests.mock(grub, "is_secure_boot", lambda: False)
    @unit_tests.mock(efi.system_info, "arch", "aarch64")
    @unit_tests.mock(efi.system_info, "version", _gen_version(7, 9))
    @unit_tests.mock(efi, "logger", GetLoggerMocked())
    @unit_tests.mock(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
    @unit_tests.mock(
        grub,
        "EFIBootInfo",
        EFIBootInfoMocked(exception=grub.BootloaderError("errmsg")),
    )
    def test_check_efi_efi_detected_non_intel(self):
        self._check_efi_critical(
            "NON_x86_64",
            "None x86_64 system detected",
            "Only x86_64 systems are supported for UEFI conversions.",
            "",
            "",
        )

    @unit_tests.mock(grub, "is_efi", lambda: True)
    @unit_tests.mock(grub, "is_secure_boot", lambda: True)
    @unit_tests.mock(efi.system_info, "arch", "x86_64")
    @unit_tests.mock(efi.system_info, "version", _gen_version(7, 9))
    @unit_tests.mock(efi, "logger", GetLoggerMocked())
    @unit_tests.mock(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
    @unit_tests.mock(
        grub,
        "EFIBootInfo",
        EFIBootInfoMocked(exception=grub.BootloaderError("errmsg")),
    )
    def test_check_efi_efi_detected_secure_boot(self):
        self._check_efi_critical(
            "SECURE_BOOT_DETECTED",
            "Secure boot detected",
            "Secure boot has been detected.",
            "The conversion with secure boot is currently not possible.",
            "To disable secure boot, follow the instructions available in this article: https://access.redhat.com/solutions/6753681",
        )
        self.assertIn("Secure boot detected.", efi.logger.info_msgs)

    @unit_tests.mock(grub, "is_efi", lambda: True)
    @unit_tests.mock(grub, "is_secure_boot", lambda: False)
    @unit_tests.mock(efi.system_info, "arch", "x86_64")
    @unit_tests.mock(efi.system_info, "version", _gen_version(7, 9))
    @unit_tests.mock(efi, "logger", GetLoggerMocked())
    @unit_tests.mock(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
    @unit_tests.mock(
        grub,
        "EFIBootInfo",
        EFIBootInfoMocked(exception=grub.BootloaderError("errmsg")),
    )
    def test_check_efi_efi_detected_bootloader_error(self):
        self._check_efi_critical(
            "BOOTLOADER_ERROR",
            "Bootloader error detected",
            "An unknown bootloader error occurred, please look at the diagnosis for more information.",
            "errmsg",
            "",
        )

    @unit_tests.mock(grub, "is_efi", lambda: True)
    @unit_tests.mock(grub, "is_secure_boot", lambda: False)
    @unit_tests.mock(efi.system_info, "arch", "x86_64")
    @unit_tests.mock(efi.system_info, "version", _gen_version(7, 9))
    @unit_tests.mock(efi, "logger", GetLoggerMocked())
    @unit_tests.mock(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
    @unit_tests.mock(grub, "EFIBootInfo", EFIBootInfoMocked(current_bootnum="0002"))
    def test_check_efi_efi_detected_nofile_entry(self):
        self.efi_action.run()
        self._check_efi_detection_log()
        warn_msg = (
            "The current UEFI bootloader '0002' is not referring to any binary UEFI file located on local"
            " EFI System Partition (ESP)."
        )
        self.assertIn(warn_msg, efi.logger.warning_msgs)

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
                    remediation=None,
                ),
            )
        )
        assert expected.issuperset(self.efi_action.messages)
        assert expected.issubset(self.efi_action.messages)

    @unit_tests.mock(grub, "is_efi", lambda: True)
    @unit_tests.mock(grub, "is_secure_boot", lambda: False)
    @unit_tests.mock(efi.system_info, "arch", "x86_64")
    @unit_tests.mock(efi.system_info, "version", _gen_version(7, 9))
    @unit_tests.mock(efi, "logger", GetLoggerMocked())
    @unit_tests.mock(os.path, "exists", lambda x: x == "/usr/sbin/efibootmgr")
    @unit_tests.mock(grub, "EFIBootInfo", EFIBootInfoMocked())
    def test_check_efi_efi_detected_ok(self):
        self.efi_action.run()
        self._check_efi_detection_log()
        self.assertEqual(len(efi.logger.warning_msgs), 0)
