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


logger = logging.getLogger(__name__)


class DuplicatePackages(actions.Action):
    id = "DUPLICATE_PACKAGES"

    def run(self):
        """Ensure that there are no duplicate system packages installed."""
        super(DuplicatePackages, self).run()

        logger.task("Prepare: Check if there are any duplicate installed packages on the system")
        output, ret = utils.run_subprocess(["/usr/bin/package-cleanup", "--dupes", "--quiet"], print_output=False)
        if not output:
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
