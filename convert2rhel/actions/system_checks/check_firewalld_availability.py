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
import os

from convert2rhel import actions, systeminfo
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)

FIREWALLD_CONFIG_FILE = "/etc/firewalld/firewalld.conf"


def _check_for_modules_cleanup_config():
    """Verify firewalld modules cleanup config

    :rtype: bool
    :returns: Whether or not the CleanupModulesOnExit is set to true in
        firewalld config.
    """
    if os.path.exists(FIREWALLD_CONFIG_FILE):
        contents = []
        with open(FIREWALLD_CONFIG_FILE, mode="r") as handler:
            contents = [line.strip() for line in handler.readlines() if line]

        # Contents list is empty for some reason, better to assume that there
        # is no content in the file that was read.
        if not contents:
            return False

        # If the config file has this option set to true/yes, then we need to
        # return True to ask the user to change it to self.
        if "CleanupModulesOnExit=yes" in contents or "CleanupModulesOnExit=true" in contents:
            return True

    return False


class CheckFirewalldAvailability(actions.Action):
    id = "CHECK_FIREWALLD_AVAILABILITY"

    def run(self):
        """Error out if the firewalld service is running on the system."""
        super(CheckFirewalldAvailability, self).run()
        logger.task("Prepare: Check that firewalld is running")

        if system_info.id == "oracle" and (system_info.version.major == 8 and system_info.version.minor >= 8):
            if systeminfo.is_systemd_managed_service_running("firewalld"):
                if _check_for_modules_cleanup_config():
                    self.set_result(
                        level="ERROR",
                        id="FIREWALLD_MODULESS_CLEANUP_ON_EXIT_CONFIG",
                        title="Firewalld is set to cleanup modules after exit.",
                        description="Firewalld running on Oracle Linux 8 can lead to a conversion failure.",
                        diagnosis="We've detected that firewalld unit is running and that causes iptables and nftables failures on Oracle Linux 8 and under certain conditions it can lead to a conversion failure.",
                        remediation=(
                            "Set the option CleanupModulesOnExit in /etc/firewalld/firewalld.conf to no prior to running convert2rhel:\n"
                            "1. sed -i -- 's/CleanupModulesOnExit=yes/CleanupModulesOnExit=no/g' /etc/firewalld/firewalld.conf\n"
                            "You can change the option back to yes after the system reboot - that is after the system boots into the RHEL kernel."
                        ),
                    )
                else:
                    # Firewalld is running but the configuration for CleanupModulesOnExit was not set to true/yes
                    self.add_message(
                        level="WARNING",
                        id="FIREWALLD_IS_RUNNING",
                        title="Firewalld is running",
                        description=(
                            "We've detected that firewalld is running and we couldn't find check for the CleanupModulesOnExit configuration. "
                            "This means that a reboot will be necessary after the conversion is done to reload the kernel modules and prevent firewalld from stop working."
                        ),
                    )
                    return

            description = "Firewalld service reported that it is not running."
            logger.info()
            self.add_message(
                level="INFO",
                id="FIREWALLD_IS_NOT_RUNNING",
                title="Firewalld not running",
                description=description,
            )
            return

        description = "Skipping the check as it is relevant only for Oracle Linux 8.8 and above."
        logger.info(description)
        self.add_message(
            level="INFO",
            id="CHECK_FIREWALLD_AVAILABILITY_SKIP",
            title="Skipping the check for firewalld availability.",
            description=description,
        )
        return
