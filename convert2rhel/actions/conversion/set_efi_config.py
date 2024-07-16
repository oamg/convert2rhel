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

import logging
import os
import shutil

from convert2rhel import actions, grub, systeminfo
from convert2rhel.grub import CENTOS_EFIDIR_CANONICAL_PATH, RHEL_EFIDIR_CANONICAL_PATH


logger = logging.getLogger(__name__)


class NewDefaultEfiBin(actions.Action):
    id = "NEW_DEFAULT_EFI_BIN"

    def run(self):
        """Check that the expected RHEL UEFI binaries exist."""
        super(NewDefaultEfiBin, self).run()

        if not grub.is_efi():
            logger.info("BIOS detected. Nothing to do.")
            return

        new_default_efibin = None
        for filename in grub.DEFAULT_INSTALLED_EFIBIN_FILENAMES:
            efi_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, filename)
            if os.path.exists(efi_path):
                logger.info("UEFI binary found: %s" % efi_path)
                new_default_efibin = efi_path
                break
            logger.debug("UEFI binary %s not found. Checking next possibility..." % efi_path)
        if not new_default_efibin:
            self.set_result(
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


class EfibootmgrUtilityInstalled(actions.Action):
    id = "EFIBOOTMGR_UTILITY_INSTALLED"
    dependencies = ("NEW_DEFAULT_EFI_BIN",)

    def run(self):
        """Check if the Efibootmgr utility is installed"""
        super(EfibootmgrUtilityInstalled, self).run()

        if not os.path.exists("/usr/sbin/efibootmgr"):
            self.set_result(
                level="ERROR",
                id="EFIBOOTMGR_UTILITY_NOT_INSTALLED",
                title="Efibootmgr utility is not installed",
                description="The /usr/sbin/efibootmgr utility is not installed.",
                remediations="Install the efibootmgr utility via YUM/DNF.",
            )


class CopyGrubFiles(actions.Action):
    id = "COPY_GRUB_FILES"
    dependencies = ("EFIBOOTMGR_UTILITY_INSTALLED",)

    def run(self):
        """Copy grub files from centos/ dir to the /boot/efi/EFI/redhat/ dir.

        The grub.cfg, grubenv, ... files are not present in the redhat/ directory
        after the conversion on a CentOS Linux system. These files are usually created
        during the OS installation by anaconda and have to be present in the
        redhat/ directory after the conversion.

        The copy of the centos/ directory should be ok. In case of the conversion
        from Oracle Linux, the redhat/ directory is already used.
        """
        super(CopyGrubFiles, self).run()

        if systeminfo.system_info.id != "centos":
            logger.debug("Skipping copying GRUB files - only related to CentOS Linux.")
            return

        # TODO(pstodulk): check behaviour for efibin from a different dir or with a different name for the possibility of
        #  the different grub content...
        # E.g. if the efibin is located in a different directory, are these two files valid?
        logger.info("Copying GRUB2 configuration files to the new UEFI directory %s." % RHEL_EFIDIR_CANONICAL_PATH)
        src_files = [
            os.path.join(CENTOS_EFIDIR_CANONICAL_PATH, filename) for filename in ["grubenv", "grub.cfg", "user.cfg"]
        ]
        required = src_files[:2]

        # If at least one file exists, this will be skipped. Otherwise, if all
        # are missing, this will be a hit.
        if not any(os.path.exists(filename) for filename in src_files):
            # Get a list of files that are missing that are required and does
            # not exist.
            missing_files = [
                filename for filename in src_files if filename in required and not os.path.exists(filename)
            ]
            # without the required files user should not reboot the system
            self.set_result(
                level="ERROR",
                id="UNABLE_TO_FIND_REQUIRED_FILE_FOR_GRUB_CONFIG",
                title="Unable to find required file for GRUB config",
                description="Unable to find the original file required for GRUB configuration at: %s"
                % ", ".join(missing_files),
            )
            return

        for src_file in src_files:
            # Check if the src_file already exists at the RHEL_EFIDR_CANONICAL_PATH
            if os.path.exists(os.path.join(RHEL_EFIDIR_CANONICAL_PATH, src_file)):
                logger.debug(
                    "The %s file already exists in %s folder. Copying skipped."
                    % (os.path.basename(src_file), RHEL_EFIDIR_CANONICAL_PATH)
                )
                continue

            dst_file = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, os.path.basename(src_file))
            logger.info("Copying '%s' to '%s'" % (src_file, dst_file))
            try:
                shutil.copy2(src_file, dst_file)
            except (OSError, IOError) as err:
                # IOError for py2 and OSError for py3
                self.set_result(
                    level="ERROR",
                    id="IO_ERROR",
                    title="I/O error",
                    description=(
                        "I/O error(%s): %s Some GRUB files have not been copied to /boot/efi/EFI/redhat."
                        % (err.errno, err.strerror)
                    ),
                )


class RemoveEfiCentos(actions.Action):
    id = "REMOVE_EFI_CENTOS"
    dependencies = ("COPY_GRUB_FILES",)

    def run(self):
        """Remove the /boot/efi/EFI/centos/ directory when no UEFI files remains.

        The centos/ directory after the conversion contains usually just grubenv,
        grub.cfg, .. files only. Which we copy into the redhat/ directory. If no
        other UEFI files are present, we can remove this dir. However, if additional
        UEFI files are present, we should keep the directory for now, until we
        deal with it.
        """
        super(RemoveEfiCentos, self).run()

        if systeminfo.system_info.id != "centos":
            logger.debug("Skipping removing EFI files - only related to CentOS Linux.")
            # nothing to do
            return
        try:
            os.rmdir(CENTOS_EFIDIR_CANONICAL_PATH)
        except OSError:
            warning_message = (
                "The folder %s is left untouched. You may remove the folder manually"
                " after you ensure there is no custom data you would need." % CENTOS_EFIDIR_CANONICAL_PATH
            )
            logger.warning(warning_message)
            self.add_message(
                level="WARNING",
                id="FOLDER_NOT_REMOVED",
                title="Folder was not removed",
                description=warning_message,
            )


class ReplaceEfiBootEntry(actions.Action):
    id = "REPLACE_EFI_BOOT_ENTRY"
    dependencies = ("REMOVE_EFI_CENTOS",)

    def run(self):
        """Replace the current UEFI bootloader entry with the RHEL one.

        The current UEFI bootloader entry could be invalid or misleading. It's
        expected that the new bootloader entry will refer to one of the standard UEFI binary
        files provided by Red Hat inside the RHEL_EFIDIR_CANONICAL_PATH.
        The new UEFI bootloader entry is always created / registered and set
        set as default.

        The current (original) UEFI bootloader entry is removed under some conditions
        (see _remove_orig_boot_entry() for more info).
        """
        super(ReplaceEfiBootEntry, self).run()

        try:
            grub.replace_efi_boot_entry()
        except grub.BootloaderError as e:
            self.set_result(
                level="ERROR",
                id="BOOTLOADER_ERROR",
                title="Bootloader error",
                description=e.message,
            )
