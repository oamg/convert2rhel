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
import os
import re

from convert2rhel import actions, backup, repo, utils
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
            self.set_result(
                level="ERROR", id="UNKNOWN_ERROR", title="An unknown error has occurred", description=str(e)
            )


class BackupRepository(actions.Action):
    id = "BACKUP_REPOSITORY"

    def run(self):
        """Backup repository files before starting conversion process"""
        loggerinst.task("Prepare: Backup Repository Files")

        super(BackupRepository, self).run()

        repo.backup_yum_repos()
        repo.backup_varsdir()


class BackupPackageFiles(actions.Action):
    id = "BACKUP_PACKAGE_FILES"

    def run(self):
        """Backup changed package files"""
        loggerinst.task("Prepare: Backup package files")

        super(BackupPackageFiles, self).run()

        backup.package_files_changes = self._get_rpm_va()

        for file in backup.package_files_changes:
            if file["status"] == "missing":
                pass  # no action needed now
            elif re.search(r"[5]", file["status"]):
                # If the MD5 checksum differs, the content of the file differs
                file["backup"] = backup.RestorableFile(file["path"])
                file["backup"].backup()

    def _get_rpm_va(self):
        """Run the rpm -Va command to get changes made to package files.
        Return them as a list of dict, for example:
        [{"status":"S5T", "file_type":"c", "path":"/etc/yum.repos.d/CentOS-Linux-AppStream.repo"}]
        """
        cmd = ["rpm", "-Va"]

        output, _ = utils.run_subprocess(cmd, print_output=False)

        return self._parse(output)

    def _parse(self, input):
        """Parse the output from input"""
        input = input.strip()
        lines = input.split("\n")
        data = []

        for line in lines:
            parsed_line = self._parse_line(line.strip())
            if parsed_line:
                data.append(parsed_line)

        return data

    def _parse_line(self, line):
        """Return {"status":"S5T", "file_type":"c", "path":"/etc/yum.repos.d/CentOS-Linux-AppStream.repo"}"""

        # Regex explanation:
        # Match missing or SM5DLUGTP (letters can be replaced by dots or ?):
        #   (missing|([S\.\?][M\.\?][5\.\?][D\.\?][L\.\?][U\.\?][G\.\?][T\.\?][P\.\?]))
        # Match whitespace: \s+
        # Match type of file, can be replaced by any whitecharacter:
        #   [cdlr\s+]
        # Match unix path:
        #   [\/\\](?:(?!\.\s+)\S)+(\.)?
        regex = r"^(missing|([S\.\?][M\.\?][5\.\?][D\.\?][L\.\?][U\.\?][G\.\?][T\.\?][P\.\?]))\s+[cdlr\s+]\s+[\/\\](?:(?!\.\s+)\S)+(\.)?$"

        ret = re.match(regex, line)

        if not ret:  # line not matching the regex
            loggerinst.debug("Skipping invalid output %s" % line)
            return

        line = line.split()

        # Replace the . (success) and ? (test could not be performed) symbols
        status = line[0].replace(".", "").replace("?", "")

        if len(line) == 2:
            # File type undefined
            file_type = None
            path = line[1]

        else:
            file_type = line[1]
            path = line[2]

        return {"status": status, "file_type": file_type, "path": path}

    @staticmethod
    def rollback_files():
        loggerinst.task("Rollback: Restore package files")
        for file in backup.package_files_changes:
            if file["status"] == "missing":
                if os.path.exists(file["path"]):
                    os.remove(file["path"])
                    loggerinst.info("Removing file %s" % file["path"])
            elif re.search(r"[5]", file["status"]):
                file["backup"].restore(rollback=False)  # debug messages are enough
