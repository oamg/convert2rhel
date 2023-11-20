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

import logging

from convert2rhel import actions
from convert2rhel.pkghandler import call_yum_cmd
from convert2rhel.toolopts import tool_opts


logger = logging.getLogger(__name__)


class CustomReposAreValid(actions.Action):
    id = "CUSTOM_REPOSITORIES_ARE_VALID"

    def run(self):
        """To prevent failures past the PONR, make sure that the enabled custom repositories are valid.
        What is meant by valid:
        - YUM/DNF is able to find the repoids (to rule out a typo)
        - the repository "baseurl" is accessible and contains repository metadata
        """
        super(CustomReposAreValid, self).run()
        logger.task("Prepare: Check if --enablerepo repositories are accessible")

        if not tool_opts.no_rhsm:
            logger.info("Skipping the check of repositories due to the use of RHSM for the conversion.")
            return

        output, ret_code = call_yum_cmd(
            command="makecache",
            args=["-v", "--setopt=*.skip_if_unavailable=False"],
            print_output=False,
        )
        if ret_code != 0:
            self.set_result(
                level="ERROR",
                id="UNABLE_TO_ACCESS_REPOSITORIES",
                title="Unable to access repositories",
                description="Access could not be made to the custom repositories.",
                diagnosis="Unable to access the repositories passed through the --enablerepo option.",
                remediation="For more details, see YUM/DNF output:\n{0}".format(output),
            )
            return

        logger.debug("Output of the previous yum command:\n{0}".format(output))
        logger.info("The repositories passed through the --enablerepo option are all accessible.")
