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

from convert2rhel import actions, checks, grub
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)

VMLINUZ_FILEPATH = "/boot/vmlinuz-%s"
"""The path to the vmlinuz file in a system."""

INITRAMFS_FILEPATH = "/boot/initramfs-%s.img"
"""The path to the initramfs image in a system."""


class KernelBootFiles(actions.Action):
    id = "KERNEL_BOOT_FILES"

    def run(self):
        """Check if the required kernel files exist and are valid under the boot partition."""
        super(KernelBootFiles, self).run()

        logger.task("Final: Check kernel boot files")

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
        logger.info("Checking if the '%s' file exists.", initramfs_file)
        is_initramfs_valid = checks.is_initramfs_file_valid(initramfs_file)

        if is_initramfs_valid or vmlinuz_exists:
            logger.info("The initramfs and vmlinuz files are valid.")
            return

        remediations = (
            "In order to fix this problem you might need to free/increase space in your boot partition" \
            " and then run the following commands in your terminal:\n"
            "1. yum reinstall {kernel_name}-{latest_installed_kernel} -y\n"
            "2. grub2-mkconfig -o {grub2_config_file}\n"
            "3. reboot".format(
                kernel_name=kernel_name,
                latest_installed_kernel=latest_installed_kernel,
                grub2_config_file=grub2_config_file
            )
        )
        logger.warning(
            "Couldn't verify the kernel boot files in the boot partition. This" \
            " might cause problems during the next boot of your system.\n" \
            "{0}".format(remediations),
        )
        self.add_message(
            level="WARNING",
            id="UNABLE_TO_VERIFY_KERNEL_BOOT_FILES",
            title="Unable to verify kernel boot files and boot partition",
            description="We failed to determine whether boot partition is configured correctly and that boot" \
                " files exists. This may cause problems during the next boot of your system.",
            remediations=remediations,
        )
