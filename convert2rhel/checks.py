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

import logging
import os

from convert2rhel.bootloader import grub
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)


VMLINUZ_FILEPATH = "/boot/vmlinuz-%s"
"""The path to the vmlinuz file in a system."""

INITRAMFS_FILEPATH = "/boot/initramfs-%s.img"
"""The path to the initramfs image in a system."""


def _is_initramfs_file_valid(filepath):
    """Internal function to verify if an initramfs file is corrupted.

    This method will rely on using lsinitrd to do the validation. If the
    lsinitrd returns other value that is not 0, then it means that the file is
    probably corrupted or may cause problems during the next reboot.

    :param filepath: The path to the initramfs file.
    :type filepath: str
    :return: A boolean to determine if the file is corrupted.
    :rtype: bool
    """
    logger.info("Checking if the '%s' file is valid.", filepath)

    if not os.path.exists(filepath):
        logger.info("The initramfs file is not present.")
        return False

    logger.debug("Checking if the '%s' file is not corrupted.", filepath)
    out, return_code = run_subprocess(
        cmd=["/usr/bin/lsinitrd", filepath],
        print_output=False,
    )

    if return_code != 0:
        logger.info("Couldn't verify initramfs file. It may be corrupted.")
        logger.debug("Output of lsinitrd: %s", out)
        return False

    return True


def check_kernel_boot_files():
    """Check if the required kernel files exist and are valid under the boot partition."""
    # For Oracle/CentOS Linux 8 the `kernel` is just a meta package, instead,
    # we check for `kernel-core`. This is not true regarding the 7.* releases.
    kernel_name = "kernel-core" if system_info.version.major >= 8 else "kernel"

    # Either the package is returned or not. The return_code will be 0 in
    # either case, so we don't care about checking for that here.
    output, _ = run_subprocess(["rpm", "-q", "--last", kernel_name], print_output=False)

    # We are parsing the latest kernel installed on the system, which at this
    # point, should be a RHEL kernel. Since we can't get the kernel version
    # from `uname -r`, as it requires a reboot in order to take place, we are
    # detecting the latest kernel by using `rpm` and figuring out which was the
    # latest kernel installed.
    latest_installed_kernel = output.split("\n")[0].split(" ")[0]
    latest_installed_kernel = latest_installed_kernel[len(kernel_name + "-") :]
    grub2_config_file = grub.get_grub_config_file()
    initramfs_file = INITRAMFS_FILEPATH % latest_installed_kernel
    vmlinuz_file = VMLINUZ_FILEPATH % latest_installed_kernel

    logger.info("Checking if the '%s' file exists.", vmlinuz_file)
    vmlinuz_exists = os.path.exists(vmlinuz_file)
    if not vmlinuz_exists:
        logger.info("The vmlinuz file is not present.")

    is_initramfs_valid = _is_initramfs_file_valid(initramfs_file)

    if not is_initramfs_valid or not vmlinuz_exists:
        logger.warning(
            "Couldn't verify the kernel boot files in the boot partition. This may cause problems during the next boot "
            "of your system.\nIn order to fix this problem you may need to free/increase space in your boot partition"
            " and then run the following commands in your terminal:\n"
            "1. yum reinstall %s-%s -y\n"
            "2. grub2-mkconfig -o %s\n"
            "3. reboot",
            kernel_name,
            latest_installed_kernel,
            grub2_config_file,
        )
    else:
        logger.info("The initramfs and vmlinuz files are valid.")
