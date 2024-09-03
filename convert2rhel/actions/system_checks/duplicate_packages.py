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

from convert2rhel import actions, utils
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)


class DuplicatePackages(actions.Action):
    id = "DUPLICATE_PACKAGES"

    def run(self):
        """Ensure that there are no duplicate system packages installed."""
        super(DuplicatePackages, self).run()

        logger.task("Prepare: Check if there are any duplicate installed packages on the system")
        output, ret_code = utils.run_subprocess(["/usr/bin/package-cleanup", "--dupes", "--quiet"], print_output=False)
        if not output:
            return
        # Catching situation when repositories cannot be accessed.
        # The output from the package-cleanup is: [Errno -2] Name or service not known
        # For el7 machines we have to depend on this output to know the check failed
        if system_info.version.major == 7 and "name or service not known" in output.lower():
            self.duplicate_packages_failure()
            return
        # For el8+ machines we can depend on just the return code being 1 to know the check failed
        if system_info.version.major >= 8 and ret_code == 1:
            self.duplicate_packages_failure()
            return
        duplicate_packages = filter(None, output.split("\n"))
        if duplicate_packages:
            self.set_result(
                level="ERROR",
                id="DUPLICATE_PACKAGES_FOUND",
                title="Duplicate packages found on the system",
                description="The system contains one or more packages with multiple versions.",
                diagnosis="The following packages have multiple versions: %s." % ", ".join(duplicate_packages),
                remediations="This error can be resolved by removing duplicate versions of the listed packages."
                " The command 'package-cleanup' can be used to automatically remove duplicate packages"
                " on the system.",
            )

    def duplicate_packages_failure(self):
        """Raise a warning in the event the duplicate packages check cannot be executed."""

        self.add_message(
            level="WARNING",
            id="DUPLICATE_PACKAGES_FAILURE",
            title="Duplicate packages check unsuccessful",
            description="The duplicate packages check did not run successfully.",
            diagnosis="The check likely failed due to lack of access to enabled repositories on the system.",
            remediations="Ensure that you can access all repositories enabled on the system and re-run convert2rhel."
            " If the issue still persists manually check if there are any package duplicates on the system and remove them to ensure a successful conversion.",
        )
