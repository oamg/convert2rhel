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


class PaygSystemCheck(actions.Action):
    id = "PAYG_SYSTEM_CHECK"

    def run(self):
        """Warn the user if their system is not supported by --payg option."""
        super(PaygSystemCheck, self).run()

        if tool_opts.payg and system_info.version.major != 7:
            self.add_message(
                level="WARNING",
                id="PAYG_COMMAND_LINE_OPTION_UNSUPPORTED",
                title="The --payg option is unsupported on this system version",
                description="The --payg command line option is supported only on RHEL 7.",
                remediation="Run convert2rhel without --payg option.",
            )

        return
