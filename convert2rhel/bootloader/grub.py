# -*- coding: utf-8 -*-
#
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

from convert2rhel import backup, systeminfo, utils
from convert2rhel.backup.files import RestorableFile
from convert2rhel.bootloader import bootloader
from convert2rhel.bootloader.bootloader import (
    CENTOS_EFIDIR_CANONICAL_PATH,
    EFI_MOUNTPOINT,
    RHEL_EFIDIR_CANONICAL_PATH,
    BootloaderError,
    EFINotUsed,
    UnsupportedEFIConfiguration,
)


logger = logging.getLogger(__name__)

GRUB2_BIOS_ENTRYPOINT = "/boot/grub2"
"""The entrypoint path of the BIOS GRUB2"""

GRUB2_BIOS_CONFIG_FILE = os.path.join(GRUB2_BIOS_ENTRYPOINT, "grub.cfg")
"""The path to the configuration file for GRUB2 in BIOS"""

GRUB2_BIOS_ENV_FILE = os.path.join(GRUB2_BIOS_ENTRYPOINT, "grubenv")
"""The path to the env file for GRUB2 in BIOS"""


def get_efi_partition():
    """Return the EFI System Partition (ESP).

    Raise EFINotUsed if UEFI is not detected.
    Raise UnsupportedEFIConfiguration when ESP is not mounted where expected.
    Raise BootloaderError if the partition can't be obtained from GRUB.
    """
    if not bootloader.is_efi():
        raise EFINotUsed("Unable to get ESP when BIOS is used.")
    if not os.path.exists(EFI_MOUNTPOINT) or not os.path.ismount(EFI_MOUNTPOINT):
        raise UnsupportedEFIConfiguration(
            "The UEFI has been detected but the ESP is not mounted in /boot/efi as required."
        )
    return _get_partition(EFI_MOUNTPOINT)


def _get_partition(directory):
    """Return the disk partition for the specified directory.

    Raise BootloaderError if the partition can't be detected.
    """
    stdout, ecode = utils.run_subprocess(["/usr/sbin/grub2-probe", "--target=device", directory], print_output=False)
    if ecode or not stdout:
        logger.error("grub2-probe returned %s. Output:\n%s" % (ecode, stdout))
        raise BootloaderError("Unable to get device information for %s." % directory)
    return stdout.strip()


def get_boot_partition():
    """Return the disk partition with /boot present.

    Raise BootloaderError if the partition can't be detected.
    """
    return _get_partition("/boot")


def _get_blk_device(device):
    """Get the block device.

    In case of the block device itself (e.g. /dev/sda), return just the block
    device. In case of a partition, return its block device:
        /dev/sda  -> /dev/sda
        /dev/sda1 -> /dev/sda

    Raise the BootloaderError when unable to get the block device.
    """
    output, ecode = utils.run_subprocess(["lsblk", "-spnlo", "name", device], print_output=False)
    if ecode:
        logger.debug("lsblk output:\n-----\n%s\n-----" % output)
        raise BootloaderError("Unable to get a block device for '%s'." % device)

    return output.strip().splitlines()[-1].strip()


def get_grub_device():
    """Get the block device on which GRUB is installed.

    We assume GRUB is on the same device as /boot (or ESP).
    """
    partition = get_efi_partition() if bootloader.is_efi() else get_boot_partition()
    return _get_blk_device(partition)


def _copy_grub_files(required, optional):
    """Copy grub files from centos/ dir to the /boot/efi/EFI/redhat/ dir.

    The grub.cfg, grubenv, ... files are not present in the redhat/ directory
    after the conversion on a CentOS Linux system. These files are usually created
    during the OS installation by anaconda and have to be present in the
    redhat/ directory after the conversion.

    The copy of the centos/ directory should be ok. In case of the conversion
    from Oracle Linux, the redhat/ directory is already used.

    Return False when any required file has not been copied or is missing.
    """
    if systeminfo.system_info.id != "centos":
        logger.debug("Skipping copying GRUB files - only related to CentOS Linux.")
        return True

    # TODO(pstodulk): check behaviour for efibin from a different dir or with a different name for the possibility of
    #  the different grub content...
    # E.g. if the efibin is located in a different directory, are these two files valid?
    logger.info("Copying GRUB2 configuration files to the new UEFI directory %s." % RHEL_EFIDIR_CANONICAL_PATH)
    flag_ok = True
    all_files = required + optional
    for filename in all_files:
        src_path = os.path.join(CENTOS_EFIDIR_CANONICAL_PATH, filename)
        dst_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, filename)
        if os.path.exists(dst_path):
            logger.debug("The %s file already exists. Copying skipped." % dst_path)
            continue
        if not os.path.exists(src_path):
            if filename in required:
                # without the required files user should not reboot the system
                logger.error("Unable to find the original file required for GRUB configuration: %s" % src_path)
                flag_ok = False
            continue
        logger.info("Copying '%s' to '%s'" % (src_path, dst_path))
        try:
            shutil.copy2(src_path, dst_path)
        except (OSError, IOError) as err:
            # IOError for py2 and OSError for py3
            logger.error("I/O error(%s): %s" % (err.errno, err.strerror))
            flag_ok = False
    return flag_ok


def get_grub_config_file():
    """Get the grub config file path.

    This method will return the grub config file, depending if it is BIOS or
    UEFI, the method will handle that automatically.

    :return: The path to the grub config file.
    :rtype: str
    """
    grub_config_path = GRUB2_BIOS_CONFIG_FILE

    if bootloader.is_efi():
        grub_config_path = os.path.join(RHEL_EFIDIR_CANONICAL_PATH, "grub.cfg")

    return grub_config_path


def update_grub_after_conversion():
    """Update GRUB2 images and config after conversion.

    This is mainly a protective measure to prevent issues in case the original distribution GRUB2 tooling
    generates images that expect different format of a config file. To be on the safe side we
    rather re-generate the GRUB2 config file and install the GRUB2 image.
    """

    backup.backup_control.push(RestorableFile(GRUB2_BIOS_CONFIG_FILE))
    backup.backup_control.push(RestorableFile(GRUB2_BIOS_ENV_FILE))

    grub2_config_file = get_grub_config_file()

    output, ret_code = utils.run_subprocess(["/usr/sbin/grub2-mkconfig", "-o", grub2_config_file], print_output=False)
    logger.debug("Output of the grub2-mkconfig call:\n%s" % output)

    if ret_code != 0:
        logger.warning("GRUB2 config file generation failed.")
        return

    if not bootloader.is_efi():
        # We don't need to call `grub2-install` in EFI systems because the image change is already being handled
        # by grub itself. We only need to regenerate the grub.cfg file in order to make it work.
        # And this can be done by calling the `grub2-mkconfig` or reinstalling some packages
        # as we are already calling `grub2-mkconfig` before of this step, then it's not necessary
        # to proceed and call it a second time.
        # Relevant bugzilla for this: https://bugzilla.redhat.com/show_bug.cgi?id=1917213
        logger.debug("Detected BIOS setup, proceeding to install the new GRUB2 images.")
        blk_device = get_grub_device()
        logger.debug("Device to install the GRUB2 image to: '%s'" % blk_device)

        output, ret_code = utils.run_subprocess(["/usr/sbin/grub2-install", blk_device], print_output=False)
        logger.debug("Output of the grub2-install call:\n%s" % output)

        if ret_code != 0:
            logger.warning("Couldn't install the new images with GRUB2.")
            return

    logger.info("Successfully updated GRUB2 on the system.")
