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
import re

from convert2rhel import actions, systeminfo
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)

# Path to the firewalld config file.
FIREWALLD_CONFIG_FILE = "/etc/firewalld/firewalld.conf"

# Regex that identify if CleanupModulesOnExit is set to either yes or true
# considering blank spaces in between the value and case insensitive.
CLEANUP_MODULES_ON_EXIT_REGEX = re.compile(r"(?i)CleanupModulesOnExit\s*=\s*(yes|true)")


def _is_modules_cleanup_enabled():
    """Verify firewalld modules cleanup config is enabled.

    :returns: Whether or not the CleanupModulesOnExit is set to true in
        firewalld config.
    :rtype: bool
    """
    # Return True is the config file does not exist.
    if not os.path.exists(FIREWALLD_CONFIG_FILE):
        logger.debug("%s does not exist." % FIREWALLD_CONFIG_FILE)
        return True

    contents = []
    with open(FIREWALLD_CONFIG_FILE, mode="r") as handler:
        contents = [line.strip() for line in handler.readlines() if line.strip()]

    # Contents list is empty for some reason, better to assume that there
    # is no content in the file that was read.
    if not contents:
        logger.debug("%s is empty." % FIREWALLD_CONFIG_FILE)
        return True

    # If the CleanupModulesOnExit is not present inside the contents list, we
    # can return True since the default behavior for firewalld is to consider
    # CleanupModulesOnExit as true. Ignoring # and ; as they are ignored in the
    # config parser for firewalld as well:
    # https://github.com/firewalld/firewalld/blob/46d54dcbdff94423686d67befc78ca8d601fce60/src/firewall/core/io/firewalld_conf.py#L85
    option_present = any(
        item.strip().startswith("CleanupModulesOnExit") for item in contents if not item.startswith(("#", ";"))
    )
    if not option_present:
        logger.debug(
            "Couldn't find CleanupModulesOnExit in firewalld.conf. Treating it as enabled because of default behavior."
        )
        return True

    # If the config file has this option set to true/yes, then we need to
    # return True to ask the user to change it to False.
    if list(filter(CLEANUP_MODULES_ON_EXIT_REGEX.match, contents)):
        logger.debug("CleanupModulesOnExit option enabled in %s" % FIREWALLD_CONFIG_FILE)
        return True

    # Default to return False as it is possible that the CleanupModulesOnExit
    # is set to no in the config already.
    logger.debug("CleanupModulesOnExit option is disabled in %s" % FIREWALLD_CONFIG_FILE)
    return False


class CheckFirewalldAvailability(actions.Action):
    id = "CHECK_FIREWALLD_AVAILABILITY"

    def run(self):
        """Error out if the firewalld service is running on the system."""
        super(CheckFirewalldAvailability, self).run()
        logger.task("Prepare: Check that firewalld is running")

        if system_info.id == "oracle" and system_info.version.major == 8 and system_info.version.minor >= 8:
            # If firewalld is not present on the system, we can just skip skip.
            if not system_info.is_rpm_installed("firewalld"):
                logger.info("The firewalld package is not installed. Nothing to do.")
                return

            if not systeminfo.is_systemd_managed_service_running("firewalld"):
                logger.info("Firewalld service reported that it is not running.")
                return

            if _is_modules_cleanup_enabled():
                self.set_result(
                    level="ERROR",
                    id="FIREWALLD_MODULES_CLEANUP_ON_EXIT_CONFIG",
                    title="Firewalld is set to cleanup modules after exit.",
                    description="Firewalld running on Oracle Linux 8 can lead to a conversion failure.",
                    diagnosis=(
                        "We've detected that firewalld unit is running and that causes iptables and nftables "
                        "failures on Oracle Linux 8 and under certain conditions it can lead to a conversion failure."
                    ),
                    remediation=(
                        "Set the option CleanupModulesOnExit in /etc/firewalld/firewalld.conf "
                        "to no prior to running convert2rhel:\n"
                        " sed -i -- 's/CleanupModulesOnExit=yes/CleanupModulesOnExit=no/g' /etc/firewalld/firewalld.conf\n && firewall-cmd --reload."
                        " You can change the option back to yes after the system reboot "
                        "- that is after the system boots into the RHEL kernel."
                    ),
                )
                return

        logger.info("Skipping the check as it is relevant only for Oracle Linux 8.8 and above.")
