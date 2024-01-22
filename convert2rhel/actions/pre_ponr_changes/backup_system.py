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

from convert2rhel import actions, backup, exceptions, repo
from convert2rhel.logger import LOG_DIR
from convert2rhel.redhatrelease import os_release_file, system_release_file
from convert2rhel.toolopts import PRE_RPM_VA_LOG_FILENAME


# Regex explanation:
# Match missing or SM5DLUGTP (letters can be replaced by dots or ?) - output of rpm -Va:
#   (missing|([S\.\?][M\.\?][5\.\?][D\.\?][L\.\?][U\.\?][G\.\?][T\.\?][P\.\?]))
# Match whitespace: \s+
# Match type of file, can be replaced by any whitecharacter:
#   [cdlr\s+]
# Match unix path:
#   [\/\\](?:(?!\.\s+)\S)+(\.)?
RPM_VA_REGEX = re.compile(
    r"^(missing|([S\.\?][M\.\?][5\.\?][D\.\?][L\.\?][U\.\?][G\.\?][T\.\?][P\.\?]))\s+[cdlr\s+]\s+[\/\\](?:(?!\.\s+)\S)+(\.)?$"
)

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

        except exceptions.CriticalError as e:
            self.set_result(
                level="ERROR",
                id=e.id,
                title=e.title,
                description=e.description,
                diagnosis=e.diagnosis,
                remediations=e.remediations,
                variables=e.variables,
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
    # BACKUP_PACKAGE_FILES should be the last one
    # Something could be backed up by this function
    # and if the MD5 differs it might be backed up for second time
    # by the BackupPackageFiles
    dependencies = ("BACKUP_REPOSITORY", "BACKUP_REDHAT_RELEASE")

    def run(self):
        """Backup changed package files"""
        super(BackupPackageFiles, self).run()

        loggerinst.task("Prepare: Backup package files")

        package_files_changes = self._get_changed_package_files()

        # Paths and files already backed up
        backed_up_files = [system_release_file.filepath, os_release_file.filepath]
        backed_up_paths = ["/etc/yum.repos.d", "/etc/yum/vars", "/etc/dnf/vars"]

        for file in package_files_changes:
            if file["status"] == "missing":
                missing_file = backup.MissingFile(file["path"])
                backup.backup_control.push(missing_file)
            elif "5" in file["status"]:
                # Check if the file is not already backed up or the path is not backed up
                if os.path.dirname(file["path"]) not in backed_up_paths and file["path"] not in backed_up_files:
                    # If the MD5 checksum differs, the content of the file differs
                    restorable_file = backup.NewRestorableFile(file["path"])
                    backup.backup_control.push(restorable_file)
                else:
                    loggerinst.debug(
                        "File {filepath} already backed up - not backing up again".format(filepath=file["path"])
                    )

    def _get_changed_package_files(self):
        """Get the output from rpm -Va command from during resolving system info
        to get changes made to package files.
        Return them as a list of dict, for example:
        [{"status":"S5T", "file_type":"c", "path":"/etc/yum.repos.d/CentOS-Linux-AppStream.repo"}]
        """
        data = []

        path = os.path.join(LOG_DIR, PRE_RPM_VA_LOG_FILENAME)

        try:
            with open(path, "r") as f:
                output = f.read()
        # Catch the IOError due Python 2 compatibility
        except IOError as err:
            if os.environ.get("CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK", None):
                loggerinst.debug("Skipping backup of the package files. CONVERT2RHEL_INCOMPLETE_ROLLBACK detected.")
                # Return empty list results in no backup of the files
                return data
            else:
                # The file should be there
                # If missing conversion is in unknown state
                loggerinst.warning("Error(%s): %s" % (err.errno, err.strerror))
                loggerinst.critical("Missing file {rpm_va_output} in it's location".format(rpm_va_output=path))

        output = output.strip()
        lines = output.split("\n")

        for line in lines:
            parsed_line = self._parse_line(line.strip())
            if parsed_line["path"] and parsed_line["status"]:
                data.append(parsed_line)

        return data

    def _parse_line(self, line):
        """Return {"status":"S5T", "file_type":"c", "path":"/etc/yum.repos.d/CentOS-Linux-AppStream.repo"}"""
        match = re.match(RPM_VA_REGEX, line)

        if not match:  # line not matching the regex
            if line.strip() != "":
                # Line is not empty string
                loggerinst.debug("Skipping invalid output %s" % line)
            return {"status": None, "file_type": None, "path": None}

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
            elif "5" in file["status"]:
                file["backup"].restore(rollback=False)  # debug messages are enough
