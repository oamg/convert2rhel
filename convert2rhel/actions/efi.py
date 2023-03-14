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
import re
import shutil
import tempfile

import rpm

from convert2rhel import __version__ as installed_convert2rhel_version
from convert2rhel import actions, grub, utils
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)

# The SSL certificate of the https://cdn.redhat.com/ server
SSL_CERT_PATH = os.path.join(utils.DATA_DIR, "redhat-uep.pem")
CDN_URL = "https://cdn.redhat.com/content/public/convert2rhel/$releasever/$basearch/os/"
RPM_GPG_KEY_PATH = os.path.join(utils.DATA_DIR, "gpg-keys", "RPM-GPG-KEY-redhat-release")

CONVERT2RHEL_REPO_CONTENT = """\
[convert2rhel]
name=Convert2RHEL Repository
baseurl=%s
gpgcheck=1
enabled=1
sslcacert=%s
gpgkey=file://%s""" % (
    CDN_URL,
    SSL_CERT_PATH,
    RPM_GPG_KEY_PATH,
)

PKG_NEVR = r"\b(\S+)-(?:([0-9]+):)?(\S+)-(\S+)\b"


class Convert2rhelLatest(actions.Action):
    id = "EFI"
    dependencies = tuple()

    def run(self):
        """Inhibit the conversion when we are not able to handle UEFI."""
        logger.task("Prepare: Check the firmware interface type (BIOS/UEFI)")
        if not grub.is_efi():
            logger.info("BIOS detected.")
            return
        logger.info("UEFI detected.")
        if not os.path.exists("/usr/sbin/efibootmgr"):
            self.status = actions.STATUS_CODE["ERROR"]
            self.error_id = "EFIBOOTMGR_NOT_FOUND"
            self.message = "Install efibootmgr to continue converting the UEFI-based system."
        if system_info.arch != "x86_64":
            logger.critical("Only x86_64 systems are supported for UEFI conversions.")
        if grub.is_secure_boot():
            logger.info("Secure boot detected.")
            self.status = actions.STATUS_CODE["ERROR"]
            self.error_id = "SECURE_BOOT_DETECTED"
            self.message = (
                "The conversion with secure boot is currently not possible.\n"
                "To disable it, follow the instructions available in this article: https://access.redhat.com/solutions/6753681"
            )

        # Get information about the bootloader. Currently the data is not used, but it's
        # good to check that we can obtain all the required data before the PONR. Better to
        # stop now than after the PONR.
        try:
            efiboot_info = grub.EFIBootInfo()
        except grub.BootloaderError as e:
            self.status = actions.STATUS_CODE["ERROR"]
            self.error_id = "BOOTLOADER_ERROR"
            self.message = e.message

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
