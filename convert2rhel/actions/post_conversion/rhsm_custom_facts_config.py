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

from convert2rhel import actions, subscription


loggerinst = logging.getLogger(__name__)


class RHSMCustomFactsConfig(actions.Action):

    id = "RHSM_CUSTOM_FACTS_CONFIG"

    dependencies = ()

    def run(self):
        super(RHSMCustomFactsConfig, self).run()
        loggerinst.task("Final: Update RHSM custom facts")
        ret_code, output = subscription.update_rhsm_custom_facts()

        if not output:
            return None

        if ret_code != 0:
            self.add_message(
                level="WARNING",
                id="FAILED_TO_UPDATE_RHSM_CUSTOM_FACTS",
                title="Failed to update RHSM custom facts",
                description="Failed to update the RHSM custom facts with return code: {0} and output: {1}.".format(
                    ret_code, output
                ),
            )
