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


import os

from convert2rhel.logger import root_logger
from convert2rhel.utils import run_subprocess


logger = root_logger.getChild(__name__)


VMLINUZ_FILEPATH = "/boot/vmlinuz-%s"
"""The path to the vmlinuz file in a system."""

INITRAMFS_FILEPATH = "/boot/initramfs-%s.img"
"""The path to the initramfs image in a system."""


def is_initramfs_file_valid(filepath):
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
