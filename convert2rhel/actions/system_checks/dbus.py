# Copyright(C) 2016 Red Hat, Inc.
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


from convert2rhel import actions, subscription
from convert2rhel.logger import root_logger
from convert2rhel.systeminfo import system_info


logger = root_logger.getChild(__name__)


class DbusIsRunning(actions.Action):
    id = "DBUS_IS_RUNNING"

    def run(self):
        """Error out if we need to register with rhsm and the dbus daemon is not running."""
        super(DbusIsRunning, self).run()
        logger.task("Check that DBus Daemon is running")

        if not subscription.should_subscribe():
            logger.info("Did not perform the check because we have been asked not to subscribe this system to RHSM.")
            return

        if system_info.dbus_running:
            logger.info("DBus Daemon is running")
            return

        self.set_result(
            level="ERROR",
            id="DBUS_DAEMON_NOT_RUNNING",
            title="Dbus daemon not running",
            description="The Dbus daemon is not running",
            diagnosis="Could not find a running DBus Daemon which is needed to register with subscription manager.",
            remediations="Please start dbus using `systemctl start dbus`",
        )
