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

import difflib
import logging
import os

from convert2rhel import actions, utils
from convert2rhel.logger import LOG_DIR
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import POST_RPM_VA_LOG_FILENAME, PRE_RPM_VA_LOG_FILENAME


logger = logging.getLogger(__name__)


class ModifiedRPMFilesDiff(actions.Action):
    id = "MODIFIED_RPM_FILES_DIFF"

    def run(self):
        """
        Get a list of modified rpm files after the conversion and
        compare it to the one from before the conversion.
        """
        super(ModifiedRPMFilesDiff, self).run()

        logger.task("Final: Show RPM files modified by the conversion")

        system_info.generate_rpm_va(log_filename=POST_RPM_VA_LOG_FILENAME)

        pre_rpm_va_log_path = os.path.join(LOG_DIR, PRE_RPM_VA_LOG_FILENAME)
        if not os.path.exists(pre_rpm_va_log_path):
            logger.info("Skipping comparison of the 'rpm -Va' output from before and after the conversion.")
            self.add_message(
                level="INFO",
                id="SKIPPED_MODIFIED_RPM_FILES_DIFF",
                title="Skipped comparison of 'rpm -Va' output from before and after the conversion.",
                description="Comparison of 'rpm -Va' output was skipped due missing output "
                "of the 'rpm -Va' run before the conversion.",
                diagnosis="This is caused mainly by using '--no-rpm-va' argument for convert2rhel.",
            )
            return

        pre_rpm_va = utils.get_file_content(pre_rpm_va_log_path, True)
        post_rpm_va_log_path = os.path.join(LOG_DIR, POST_RPM_VA_LOG_FILENAME)
        post_rpm_va = utils.get_file_content(post_rpm_va_log_path, True)
        modified_rpm_files_diff = "\n".join(
            difflib.unified_diff(
                pre_rpm_va,
                post_rpm_va,
                fromfile=pre_rpm_va_log_path,
                tofile=post_rpm_va_log_path,
                n=0,
                lineterm="",
            )
        )

        if modified_rpm_files_diff:
            logger.info(
                "Comparison of modified rpm files from before and after the conversion:\n%s" % modified_rpm_files_diff
            )
            self.add_message(
                level="INFO",
                id="FOUND_MODIFIED_RPM_FILES",
                title="Modified rpm files from before and after the conversion were found.",
                description="Comparison of modified rpm files from before and after "
                "the conversion: \n%s" % modified_rpm_files_diff,
            )
