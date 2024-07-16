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

from convert2rhel import actions, backup, grub, utils
from convert2rhel.backup.files import RestorableFile


logger = logging.getLogger(__name__)


class UpdateGrub(actions.Action):
    id = "UPDATE_GRUB"

    def run(self):
        """Update GRUB2 images and config after conversion.

        This is mainly a protective measure to prevent issues in case the original distribution GRUB2 tooling
        generates images that expect different format of a config file. To be on the safe side we
        rather re-generate the GRUB2 config file and install the GRUB2 image.
        """
        super(UpdateGrub, self).run()

        logger.task("Final: Update GRUB2 configuration")

        backup.backup_control.push(RestorableFile(grub.GRUB2_BIOS_CONFIG_FILE))
        backup.backup_control.push(RestorableFile(grub.GRUB2_BIOS_ENV_FILE))

        grub2_config_file = grub.get_grub_config_file()

        output, ret_code = utils.run_subprocess(
            ["/usr/sbin/grub2-mkconfig", "-o", grub2_config_file], print_output=False
        )
        logger.debug("Output of the grub2-mkconfig call:\n%s" % output)

        if ret_code != 0:
            logger.warning("GRUB2 config file generation failed.")
            self.add_message(
                level="WARNING",
                id="GRUB2_CONFIG_CREATION_FAILED",
                title="GRUB2 config file generation failed",
                description="The GRUB2 config file generation failed.",
            )
            return

        if not grub.is_efi():
            # We don't need to call `grub2-install` in EFI systems because the image change is already being handled
            # by grub itself. We only need to regenerate the grub.cfg file in order to make it work.
            # And this can be done by calling the `grub2-mkconfig` or reinstalling some packages
            # as we are already calling `grub2-mkconfig` before of this step, then it's not necessary
            # to proceed and call it a second time.
            # Relevant bugzilla for this: https://bugzilla.redhat.com/show_bug.cgi?id=1917213
            logger.debug("Detected BIOS setup, proceeding to install the new GRUB2 images.")
            try:
                blk_device = grub.get_grub_device()
            # two kinds of bootloader errors so we output the specific issue in diagnosis
            except grub.BootloaderError as e:
                self.set_result(
                    level="ERROR",
                    id="BOOTLOADER_ERROR",
                    title="Bootloader error detected",
                    description="An unknown bootloader error occurred, please look at the diagnosis for more information.",
                    diagnosis=str(e),
                )
                return

            logger.debug("Device to install the GRUB2 image to: '%s'" % blk_device)

            output, ret_code = utils.run_subprocess(["/usr/sbin/grub2-install", blk_device], print_output=False)
            logger.debug("Output of the grub2-install call:\n%s" % output)

            if ret_code != 0:
                logger.warning("Couldn't install the new images with GRUB2.")
                self.add_message(
                    level="WARNING",
                    id="GRUB2_INSTALL_FAILED",
                    title="Couldn't install the new images with GRUB2",
                    description="The new images could not be installed with GRUB2.",
                )
                return

        logger.info("Successfully updated GRUB2 on the system.")
