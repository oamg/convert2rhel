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

import datetime
import logging

from convert2rhel import actions
from convert2rhel.systeminfo import EUS_MINOR_VERSIONS, system_info
from convert2rhel.toolopts import tool_opts


logger = logging.getLogger(__name__)


class EusSystemCheck(actions.Action):
    id = "EUS_SYSTEM_CHECK"

    def run(self):
        """Warn the user if their system is under EUS and past the EUS release date without using the --eus cli option."""
        super(EusSystemCheck, self).run()

        current_version = "%s.%s" % (system_info.version.major, system_info.version.minor)
        eus_versions = list(EUS_MINOR_VERSIONS.keys())
        if current_version in eus_versions:
            eus_release_date = EUS_MINOR_VERSIONS.get(current_version, False)
            # Turn eus_release_date into a datetime object
            eus_release_date = datetime.datetime.strptime(eus_release_date, "%Y-%m-%d").date()
            current_datetime = datetime.date.today()

            # warning message if the eus release date is past and the --eus option is not set
            if not tool_opts.eus and current_datetime > eus_release_date:
                self.add_message(
                    level="WARNING",
                    id="EUS_COMMAND_LINE_OPTION_UNUSED",
                    title="The --eus command line option is unused",
                    description="Current system version is under Extended Update Support (EUS). You may want to consider using the --eus"
                    " command line option to land on a system patched with the latest security errata.",
                )
        return
