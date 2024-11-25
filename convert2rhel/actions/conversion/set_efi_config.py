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

from convert2rhel import actions, grub, systeminfo
from convert2rhel.grub import CENTOS_EFIDIR_CANONICAL_PATH, RHEL_EFIDIR_CANONICAL_PATH
from convert2rhel.logger import root_logger


logger = root_logger.getChild(__name__)


class NewDefaultEfiBin(actions.Action):
    id = "NEW_DEFAULT_EFI_BIN"
    dependencies = ("FIX_DEFAULT_KERNEL",)

    def run(self):
        """Check that the expected RHEL UEFI binaries exist."""
        super(NewDefaultEfiBin, self).run()

        logger.task("Configure the bootloader")

        if not grub.is_efi():
            logger.info(
                "Unable to collect data about UEFI on a BIOS system, did not perform check of RHEL UEFI binaries."
            )
            return

        new_default_efibin = None
        missing_binaries = []

        for filename in grub.DEFAULT_INSTALLED_EFIBIN_FILENAMES:
            efi_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, filename)
            if os.path.exists(efi_path):
                logger.info("UEFI binary found: {}".format(efi_path))
                new_default_efibin = efi_path
                break
            logger.debug("UEFI binary {} not found. Checking next possibility...".format(efi_path))
            missing_binaries.append(efi_path)
        if not new_default_efibin:
            self.set_result(
                level="ERROR",
                id="NOT_FOUND_RHEL_UEFI_BINARIES",
                title="RHEL UEFI binaries not found",
                description="None of the expected RHEL UEFI binaries exist.",
                diagnosis="Bootloader couldn't be migrated due to missing RHEL EFI binaries: {} .".format(
                    ", ".join(missing_binaries)
                ),
                remediations=(
                    "Verify the bootloader configuration as follows and reboot the system."
                    " Ensure that `grubenv` and `grub.cfg` files"
                    " are present in the {} directory. Verify that `efibootmgr -v`"
                    " shows a bootloader entry for Red Hat Enterprise Linux"
                    " that points to to '\\EFI\\redhat\\shimx64.efi'.".format(grub.RHEL_EFIDIR_CANONICAL_PATH)
                ),
            )


class EfibootmgrUtilityInstalled(actions.Action):
    id = "EFIBOOTMGR_UTILITY_INSTALLED"
    dependencies = ("NEW_DEFAULT_EFI_BIN",)

    def run(self):
        """Check if the Efibootmgr utility is installed"""
        super(EfibootmgrUtilityInstalled, self).run()

        if not grub.is_efi():
            logger.info(
                "Unable to collect data about UEFI on a BIOS system, did not perform check of UEFI boot manager"
                " utility."
            )
            return

        if not os.path.exists("/usr/sbin/efibootmgr"):
            self.set_result(
                level="ERROR",
                id="NOT_INSTALLED_EFIBOOTMGR_UTILITY",
                title="UEFI boot manager utility not found",
                description="Couldn't find the UEFI boot manager which is required for us to install and verify a RHEL boot entry.",
                remediations="Install the efibootmgr utility using the following command:\n\n 1. yum install efibootmgr",
            )


class MoveGrubFiles(actions.Action):
    id = "MOVE_GRUB_FILES"
    dependencies = ("EFIBOOTMGR_UTILITY_INSTALLED",)

    def run(self):
        """Move grub files from centos/ dir to the /boot/efi/EFI/redhat/ dir.

        The grub.cfg, grubenv, ... files are not present in the redhat/ directory
        after the conversion on a CentOS Linux system. These files are usually created
        during the OS installation by anaconda and have to be present in the
        redhat/ directory after the conversion.

        The move of the centos/ directory should be ok. In case of the conversion
        from Oracle Linux, the redhat/ directory is already used.
        """
        super(MoveGrubFiles, self).run()

        if not grub.is_efi():
            logger.info("Unable to collect data about UEFI on a BIOS system, did not perform moving of Grub2 files.")
            return

        if systeminfo.system_info.id != "centos":
            logger.debug("Did not perform moving of GRUB files - only related to CentOS Linux.")
            return

        # TODO(pstodulk): check behaviour for efibin from a different dir or with a different name for the possibility of
        #  the different grub content...
        # E.g. if the efibin is located in a different directory, are these two files valid?
        logger.info("Moving GRUB2 configuration files to the new UEFI directory {}.".format(RHEL_EFIDIR_CANONICAL_PATH))
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
                title="Couldn't find system GRUB config",
                description="Couldn't find one of the GRUB config files in the current system which is required for configuring UEFI for RHEL: {}".format(
                    ", ".join(missing_files)
                ),
            )
            return

        for src_file in src_files:
            # Skip non-existing file in destination directory
            if not os.path.exists(src_file):
                logger.debug(
                    "The {} file does not exist in {} folder. Moving skipped.".format(
                        os.path.basename(src_file), CENTOS_EFIDIR_CANONICAL_PATH
                    )
                )
                continue
            # Skip already existing file in destination directory
            dst_file = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, os.path.basename(src_file))
            if os.path.exists(dst_file):
                logger.debug(
                    "The {} file already exists in {} folder. Moving skipped.".format(
                        os.path.basename(src_file), RHEL_EFIDIR_CANONICAL_PATH
                    )
                )
                continue

            logger.info("Moving '{}' to '{}'.".format(src_file, dst_file))

            try:
                shutil.move(src_file, dst_file)
            except (OSError, IOError) as err:
                # IOError for py2 and OSError for py3
                self.set_result(
                    level="ERROR",
                    id="GRUB_FILES_NOT_MOVED_TO_BOOT_DIRECTORY",
                    title="GRUB files have not been moved to boot directory",
                    description=(
                        "I/O error({}): '{}'. Some GRUB files have not been moved to /boot/efi/EFI/redhat.".format(
                            err.errno, err.strerror
                        )
                    ),
                )


class RemoveEfiCentos(actions.Action):
    id = "REMOVE_EFI_CENTOS"
    dependencies = ("MOVE_GRUB_FILES",)

    def run(self):
        """Remove the /boot/efi/EFI/centos/ directory when no UEFI files remains.

        The centos/ directory after the conversion contains usually just grubenv,
        grub.cfg, .. files only. Which we move into the redhat/ directory. If no
        other UEFI files are present, we can remove this dir. However, if additional
        UEFI files are present, we should keep the directory for now, until we
        deal with it.
        """
        super(RemoveEfiCentos, self).run()

        if not grub.is_efi():
            logger.info(
                "Unable to collect data about UEFI on a BIOS system, did not perform removal of CentOS UEFI directory."
            )
            return

        if systeminfo.system_info.id != "centos":
            logger.debug("Did not perform removal of EFI files - only related to CentOS Linux.")
            # nothing to do
            return
        try:
            os.rmdir(CENTOS_EFIDIR_CANONICAL_PATH)
        except (OSError, IOError) as err:
            warning_message = (
                "Failed to remove the {dir} directory as files still exist."
                " During conversion we make sure to move over files needed to their RHEL counterpart."
                " However, some files we didn't expect likely exist in the directory that needs human oversight."
                " Make sure that the files within the directory is taken care of and proceed with deleting the directory"
                " manually after conversion. We received error: '{err}'."
            ).format(dir=CENTOS_EFIDIR_CANONICAL_PATH, err=err)

            logger.warning(warning_message)
            self.add_message(
                level="WARNING",
                id="NOT_REMOVED_CENTOS_UEFI_DIRECTORY",
                title="CentOS UEFI directory couldn't be removed",
                description=warning_message,
            )


class ReplaceEfiBootEntry(actions.Action):
    id = "REPLACE_EFI_BOOT_ENTRY"
    dependencies = ("REMOVE_EFI_CENTOS", "EFIBOOTMGR_UTILITY_INSTALLED")

    def run(self):
        """Replace the current UEFI bootloader entry with the RHEL one.

        The current UEFI bootloader entry could be invalid or misleading. It's
        expected that the new bootloader entry will refer to one of the standard UEFI binary
        files provided by Red Hat inside the RHEL_EFIDIR_CANONICAL_PATH.
        The new UEFI bootloader entry is always created / registered and
        set as default.

        The current (original) UEFI bootloader entry is removed under some conditions
        (see `py:grub._remove_orig_boot_entry()` for more info).
        """
        super(ReplaceEfiBootEntry, self).run()

        if not grub.is_efi():
            logger.info(
                "Unable to collect data about UEFI on a BIOS system, did not perform UEFI bootloader "
                "entry replacement."
            )
            return

        try:
            grub.replace_efi_boot_entry()
        except grub.BootloaderError as e:
            self.set_result(
                level="ERROR",
                id="FAILED_TO_REPLACE_UEFI_BOOT_ENTRY",
                title="Failed to replace UEFI boot entry to RHEL",
                description=(
                    "As the current UEFI bootloader entry could be invalid or missing we need to ensure that a "
                    "RHEL UEFI entry exists. The UEFI boot entry could not be replaced due to the following"
                    " error: '{err}'".format(err=e.message)
                ),
            )
