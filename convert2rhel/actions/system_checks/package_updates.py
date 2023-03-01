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

from convert2rhel import actions, pkgmanager, utils
from convert2rhel.pkghandler import get_total_packages_to_update
from convert2rhel.repo import get_hardcoded_repofiles_dir
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)


class PackageUpdates(actions.Action):
    id = "PACKAGE_UPDATES"

    def run(self):
        """Ensure that the system packages installed are up-to-date."""
        super(PackageUpdates, self).run()
        logger.task("Prepare: Check if the installed packages are up-to-date")

        if system_info.id == "oracle" and system_info.corresponds_to_rhel_eus_release():
            logger.info(
                "Skipping the check because there are no publicly available %s %d.%d repositories available."
                % (system_info.name, system_info.version.major, system_info.version.minor)
            )
            return

        reposdir = get_hardcoded_repofiles_dir()

        if reposdir and not system_info.has_internet_access:
            logger.warning("Skipping the check as no internet connection has been detected.")
            return

        try:
            packages_to_update = get_total_packages_to_update(reposdir=reposdir)
        except (utils.UnableToSerialize, pkgmanager.RepoError) as e:
            # As both yum and dnf have the same error class (RepoError), to identify any problems when interacting with the
            # repositories, we use this to catch exceptions when verifying if there is any packages to update on the system.
            # Beware that the `RepoError` exception is based on the `pkgmanager` module and the message sent to the output
            # can differ depending if the code is running in RHEL7 (yum) or RHEL8 (dnf).
            logger.warning(
                "There was an error while checking whether the installed packages are up-to-date. Having an updated system is"
                " an important prerequisite for a successful conversion. Consider verifyng the system is up to date manually"
                " before proceeding with the conversion."
            )
            logger.warning(str(e))
            return

        if len(packages_to_update) > 0:
            repos_message = (
                "on the enabled system repositories"
                if not reposdir
                else "on repositories defined in the %s folder" % reposdir
            )
            logger.warning(
                "The system has %s package(s) not updated based %s.\n"
                "List of packages to update: %s.\n\n"
                "Not updating the packages may cause the conversion to fail.\n"
                "Consider updating the packages before proceeding with the conversion."
                % (len(packages_to_update), repos_message, " ".join(packages_to_update))
            )
        else:
            logger.info("System is up-to-date.")
