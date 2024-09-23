# Copyright(C) 2016 Red Hat, Inc.
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


import os.path

from convert2rhel import actions, grub
from convert2rhel.logger import root_logger
from convert2rhel.systeminfo import system_info


logger = root_logger.getChild(__name__)


class Efi(actions.Action):
    id = "EFI"

    def run(self):
        """Inhibit the conversion when we are not able to handle UEFI."""
        super(Efi, self).run()

        logger.task("Prepare: Check the firmware interface type (BIOS/UEFI)")
        if not grub.is_efi():
            logger.info("BIOS detected.")
            return
        logger.info("UEFI detected.")
        if system_info.arch != "x86_64":
            self.set_result(
                level="ERROR",
                id="NON_x86_64",
                title="None x86_64 system detected",
                description="Only x86_64 systems are supported for UEFI conversions.",
            )
            return
        if not os.path.exists("/usr/sbin/efibootmgr"):
            self.set_result(
                level="ERROR",
                id="EFIBOOTMGR_NOT_FOUND",
                title="EFI boot manager not found",
                description="The EFI boot manager could not be found.",
                diagnosis="The EFI boot manager tool - efibootmgr could not be found on your system",
                remediations="Install efibootmgr to continue converting the UEFI-based system.",
            )
            return
        if grub.is_secure_boot():
            logger.info("Secure boot detected.")
            self.set_result(
                level="ERROR",
                id="SECURE_BOOT_DETECTED",
                title="Secure boot detected",
                description="Secure boot has been detected.",
                diagnosis="The conversion with secure boot is currently not possible.",
                remediations="To disable secure boot, follow the instructions available in this article: https://access.redhat.com/solutions/6753681",
            )
            return

        # Get information about the bootloader. Currently, the data is not used, but it's
        # good to check that we can obtain all the required data before the PONR.
        try:
            efiboot_info = grub.EFIBootInfo()
            grub.get_device_number(grub.get_efi_partition())
        except grub.BootloaderError as e:
            self.set_result(
                level="ERROR",
                id="BOOTLOADER_ERROR",
                title="Bootloader error detected",
                description="An unknown bootloader error occurred, please look at the diagnosis for more information.",
                diagnosis=str(e),
            )
            return

        if not efiboot_info.entries[efiboot_info.current_bootnum].is_referring_to_file():
            # NOTE(pstodulk): I am not sure what could be consequences after the conversion, as the
            # new UEFI bootloader entry is created referring to a RHEL UEFI binary.
            logger.warning(
                "The current UEFI bootloader '{}' is not referring to any binary UEFI"
                " file located on local EFI System Partition (ESP).".format(efiboot_info.current_bootnum)
            )
            self.add_message(
                level="WARNING",
                id="UEFI_BOOTLOADER_MISMATCH",
                title="UEFI bootloader mismatch",
                description="There was a UEFI bootloader mismatch.",
                diagnosis=(
                    "The current UEFI bootloader '{}' is not referring to any binary UEFI"
                    " file located on local EFI System Partition (ESP).".format(efiboot_info.current_bootnum)
                ),
            )
        # TODO(pstodulk): print warning when multiple orig. UEFI entries point
        # to the original system (e.g. into the centos/ directory..). The point is
        # that only the current UEFI bootloader entry is handled.
        # If e.g. on CentOS Linux, other entries with CentOS labels could be
        # invalid (or at least misleading) as the OS will be replaced by RHEL
