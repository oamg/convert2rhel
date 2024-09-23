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

from convert2rhel import actions, logger, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


loggerinst = logger.root_logger.getChild(__name__)


class LockReleaseverInRHELRepositories(actions.Action):
    id = "LOCK_RELEASEVER_IN_RHEL_REPOSITORIES"
    dependencies = ()

    def run(self):
        """Lock the releasever in the RHEL repositories located under /etc/yum.repos.d/redhat.repo

        After converting to a RHEL EUS minor version, we need to lock the releasever in the redhat.repo file to prevent
        future errors such as, running `yum update` and not being able to find the repositories metadata.

        .. note::
        This function should only run if the system corresponds to a RHEL EUS version to make sure the converted system
        keeps receiving updates for the specific EUS minor version instead of the latest minor version which is the
        default.
        """
        super(LockReleaseverInRHELRepositories, self).run()
        loggerinst.task("Convert: Lock releasever in RHEL repositories")
        # We only lock the releasever on rhel repos if we detect that the running system is an EUS correspondent and if
        # rhsm is used, otherwise, there's no need to lock the releasever as the subscription-manager won't be
        # available.
        if not system_info.eus_system or tool_opts.no_rhsm:
            loggerinst.info("Skipping locking RHEL repositories to a specific EUS minor version.")
            self.add_message(
                id="SKIPPED_LOCK_RELEASEVER_IN_RHEL_REPOSITORIES",
                level="INFO",
                title="Skipped releasever lock",
                description="Releasever lock is needed only when converting to RHEL EUS using RHSM.",
            )
            return
        loggerinst.info(
            "Updating /etc/yum.repos.d/rehat.repo to point to RHEL {} instead of the default latest minor version.".format(
                system_info.releasever
            )
        )
        cmd = [
            "subscription-manager",
            "release",
            "--set={}".format(system_info.releasever),
        ]
        _, ret_code = utils.run_subprocess(cmd, print_output=False)
        if ret_code != 0:
            loggerinst.warning("Locking RHEL repositories failed.")
            return
        loggerinst.info("RHEL repositories locked to the {} minor version.".format(system_info.releasever))
