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

from convert2rhel import actions, repo
from convert2rhel.redhatrelease import os_release_file, system_release_file


loggerinst = logging.getLogger(__name__)


class BackupRedhatRelease(actions.Action):
    id = "BACKUP_REDHAT_RELEASE"

    def run(self):
        """Backup redhat release file before starting conversion process"""
        loggerinst.task("Prepare: Backup Redhat Release Files")

        super(BackupRedhatRelease, self).run()

        try:
            # TODO(r0x0d): We need to keep calling those global objects from
            # redhatrelease.py because of the below code:
            # https://github.com/oamg/convert2rhel/blob/v1.2/convert2rhel/subscription.py#L189-L200
            system_release_file.backup()
            os_release_file.backup()
        except SystemExit as e:
            # TODO(pr-watson): Places where we raise SystemExit and need to be
            # changed to something more specific.
            # Raised in module redhatrelease on lines 49 and 60
            #   - If unable to find the /etc/system-release file,
            #     SystemExit is raised
            self.set_result(status="ERROR", error_id="UNKNOWN_ERROR", message=str(e))


class BackupRepository(actions.Action):
    id = "BACKUP_REPOSITORY"

    def run(self):
        """Backup repository files before starting conversion process"""
        loggerinst.task("Prepare: Backup Repository Files")

        super(BackupRepository, self).run()

        repo.backup_yum_repos()
        repo.backup_varsdir()
