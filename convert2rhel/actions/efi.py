# Copyright(C) 2023 Red Hat, Inc.
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

import logging
import os.path

from convert2rhel import actions, grub, utils
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)


class Efi(actions.Action):
    id = "EFI"

    def run(self):
        """Inhibit the conversion when we are not able to handle UEFI."""
        logger.task("Prepare: Check the firmware interface type (BIOS/UEFI)")
        if not grub.is_efi():
            logger.info("BIOS detected.")
            return
        logger.info("UEFI detected.")
        if not os.path.exists("/usr/sbin/efibootmgr"):
            self.set_result(
                status="ERROR",
                error_id="EFIBOOTMGR_NOT_FOUND",
                message="Install efibootmgr to continue converting the UEFI-based system.",
            )
            return
        if system_info.arch != "x86_64":
            self.set_result(
                status="ERROR",
                error_id="NON_x86_64",
                message="Only x86_64 systems are supported for UEFI conversions.",
            )
            return
        if grub.is_secure_boot():
            logger.info("Secure boot detected.")
            self.set_result(
                status="ERROR",
                error_id="SECURE_BOOT_DETECTED",
                message=(
                    "The conversion with secure boot is currently not possible.\n"
                    "To disable it, follow the instructions available in this article: https://access.redhat.com/solutions/6753681"
                ),
            )

            return

        # Get information about the bootloader. Currently the data is not used, but it's
        # good to check that we can obtain all the required data before the PONR. Better to
        # stop now than after the PONR.
        try:
            efiboot_info = grub.EFIBootInfo()
        except grub.BootloaderError as e:
            self.set_result(status="ERROR", error_id="BOOTLOADER_ERROR", message="%s" % e)
            return

        if not efiboot_info.entries[efiboot_info.current_bootnum].is_referring_to_file():
            # NOTE(pstodulk): I am not sure what could be consequences after the conversion, as the
            # new UEFI bootloader entry is created referring to a RHEL UEFI binary.
            logger.warning(
                "The current UEFI bootloader '%s' is not referring to any binary UEFI"
                " file located on local EFI System Partition (ESP)." % efiboot_info.current_bootnum
            )
        # TODO(pstodulk): print warning when multiple orig. UEFI entries point
        # to the original system (e.g. into the centos/ directory..). The point is
        # that only the current UEFI bootloader entry is handled.
        # If e.g. on CentOS Linux, other entries with CentOS labels could be
        # invalid (or at least misleading) as the OS will be replaced by RHEL