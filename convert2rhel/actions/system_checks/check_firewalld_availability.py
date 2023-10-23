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

from convert2rhel import actions, systeminfo
from convert2rhel.systeminfo import system_info


logger = logging.getLogger(__name__)


class CheckFirewalldAvailability(actions.Action):
    id = "CHECK_FIREWALLD_AVAILABILITY"

    def run(self):
        """Error out if the firewalld service is running on the system."""
        super(CheckFirewalldAvailability, self).run()
        logger.task("Prepare: Check that firewalld is running")

        if system_info.id == "oracle" and (system_info.version.major == 8 and system_info.version.minor >= 8):
            if systeminfo.is_systemd_managed_service_running("firewalld"):
                self.set_result(
                    level="ERROR",
                    id="FIREWALLD_RUNNING",
                    title="Firewalld is running",
                    description="Firewalld is running and can cause problems during the package replacement phase.",
                    diagnosis="We've detected that firewalld unit is running and might cause problems related to kernel modules after the conversion is done.",
                    remediation=(
                        "Stop firewalld by using the `systemctl stop firewalld` command. This will prevent errors while convert2rhel replaces the system packages"
                        " and the kernel, whoever, that might not prevent errors from appearing the firewalld logs after the conversion. After the conversion is done,"
                        " reboot the system to load the new RHEL kernel modules and start firewalld with `systemctl start firewalld` once more."
                    ),
                )
                return

            logger.info("Firewalld is not running.")
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
