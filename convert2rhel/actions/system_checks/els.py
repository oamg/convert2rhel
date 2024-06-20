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

import datetime
import logging

from convert2rhel import actions
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


logger = logging.getLogger(__name__)

ELS_START_DATE = "2024-07-01"


class ElsSystemCheck(actions.Action):
    id = "ELS_SYSTEM_CHECK"

    def run(self):
        """Warn the user if their system is under ELS and past the ELS release date without using the --els cli option."""
        super(ElsSystemCheck, self).run()

        if system_info.version.major == 7:
            current_datetime = datetime.date.today()
            # Turn ELS_START_DATE into a datetime object
            els_start_date = datetime.datetime.strptime(ELS_START_DATE, "%Y-%m-%d").date()

            print(current_datetime > els_start_date)
            # warning message if the els release date is past and the --els option is not set
            if not tool_opts.els and current_datetime > els_start_date:
                self.add_message(
                    level="WARNING",
                    id="ELS_COMMAND_LINE_OPTION_UNUSED",
                    title="The --els command line option is unused",
                    description=(
                        "Current system version is under Extended Lifecycle Support (ELS). You may want to "
                        "consider using the --els command line option to land on a system patched with the latest "
                        "security errata.",
                    ),
                )
        return
