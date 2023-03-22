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

from convert2rhel import actions
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


logger = logging.getLogger(__name__)


class DbusIsRunning(actions.Action):
    id = "DBUS_IS_RUNNING"

    def run(self):
        """Error out if we need to register with rhsm and the dbus daemon is not running."""
        super(DbusIsRunning, self).run()
        logger.task("Prepare: Check that DBus Daemon is running")

        if tool_opts.no_rhsm:
            logger.info("Skipping the check because we have been asked not to subscribe this system to RHSM.")
            return

        if system_info.dbus_running:
            logger.info("DBus Daemon is running")
            return

        self.set_result(
            status="ERROR",
            error_id="DBUS_DAEMON_NOT_RUNNING",
            message=(
                "Could not find a running DBus Daemon which is needed to register with subscription manager.\n"
                "Please start dbus using `systemctl start dbus`"
            ),
        )
