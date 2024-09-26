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

from convert2rhel import actions, utils
from convert2rhel.logger import root_logger


logger = root_logger.getChild(__name__)


class GrubValidity(actions.Action):
    id = "GRUB_VALIDITY"

    def run(self):
        """
        Execute grub2-mkconfig and report an error if it fails to execute. A failure means that the grub file
        is invalid.
        """
        super(GrubValidity, self).run()
        logger.task("Prepare: Check if the grub file is valid")
        output, ret_code = utils.run_subprocess(["grub2-mkconfig"], print_output=False)

        if ret_code != 0:
            self.set_result(
                level="ERROR",
                id="INVALID_GRUB_FILE",
                title="Grub boot entry file is invalid",
                description="The grub file seems to be invalid leaving the system in a"
                " non-clean state and must be fixed before continuing the conversion"
                " to ensure a smooth process.",
                remediations="Check the grub file inside `/etc/default` directory and remove any "
                "misconfigurations, then re-run the conversion.",
            )
