# -*- coding: utf-8 -*-
#
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

import hashlib
import logging
import os
import shutil

from convert2rhel import exceptions
from convert2rhel.backup import BACKUP_DIR, RestorableChange


loggerinst = logging.getLogger(__name__)


class RestorableFile(RestorableChange):
    def __init__(self, filepath):
        super(RestorableFile, self).__init__()
        # The filepath we want to back up needs to start with at least a `/`,
        # otherwise, let's error out and warn the developer/user that the
        # filepath is not what we expect. This is mostly intended to be an
        # error to catch during development, not runtime.
        if not os.path.isabs(filepath):
            raise TypeError("Filepath needs to be an absolute path.")

        # We don't support directory globs in here *yet*, so let's prevent to
        # pass a directory here as well.
        if os.path.isdir(filepath):
            raise TypeError("Path must be a file not a directory.")

        self.filepath = filepath
        self.backup_path = None

    def enable(self):
        """Save current version of a file"""
        # Prevent multiple backup
        if self.enabled:
            return

        loggerinst.info("Backing up %s." % self.filepath)
        if os.path.isfile(self.filepath):
            try:
                backup_path = self._hash_backup_path()
                self.backup_path = backup_path
                shutil.copy2(self.filepath, backup_path)
                loggerinst.debug("Copied %s to %s." % (self.filepath, backup_path))
            except (OSError, IOError) as err:
                # IOError for py2 and OSError for py3
                loggerinst.critical_no_exit("Error(%s): %s" % (err.errno, err.strerror))
                raise exceptions.CriticalError(
                    id_="FAILED_TO_SAVE_FILE_TO_BACKUP_DIR",
                    title="Failed to copy file to the backup directory.",
                    description=(
                        "Copying the current file has failed. This can lead to inconsistency during the rollbacks as "
                        "convert2rhel won't be able to restore the file in case of failures."
                        "In the current case, we encountered a failure while performing that backup so it is unsafe "
                        "to continue. See the diagnosis section to identify which problem ocurred during the backup."
                    ),
                    diagnosis="Failed to backup %s. Errno: %s, Error: %s" % (self.filepath, err.errno, err.strerror),
                )
        else:
            loggerinst.info("Can't find %s.", self.filepath)
            return

        # Set the enabled value
        super(RestorableFile, self).enable()

    def _hash_backup_path(self):
        """Hash the backup path for a given file based on its directory path.

        .. example::
            Below, we can see an example of the output of this function.
            It will return the backup path of a given file, alongside with a
            hashed directory name based on the `py:os.path.dirname()` of the
            given file.
            >>> filepath = "/etc/logrotate.d/yum"
            >>> rf = NewRestorableFile(filepath)
            >>> hashed_directory = rf._hash_backup_path()
            >>> print(hashed_directory) # /var/lib/convert2rhel/backup/48a9cd4be5179aee315190d2107264af

        :returns str: The hashed backup path based on the `py:BACKUP_DIR`
            constant.
        """
        path, filename = os.path.split(self.filepath)
        hashed_directory = os.path.join(BACKUP_DIR, hashlib.md5(path.encode()).hexdigest())

        if not os.path.exists(hashed_directory):
            os.makedirs(hashed_directory, mode=0o755)

        filepath = os.path.join(hashed_directory, filename)
        return filepath

    def restore(self, rollback=True):
        """Restore a previously backed up file

        :arg rollback: bool value to decide if there is need print the rollback messages.
            This argument can also be used during conversion for restoring some file needed
            for conversion and thus won't need rollback messages.

            .. warning::
                Exceptions are not handled and left for handling by the calling code.

        :raises OSError: When the backed up file is missing.
        :raises IOError: When the backed up file is missing.
        """
        if rollback:
            loggerinst.task("Rollback: Restore %s from backup" % self.filepath)
        else:
            loggerinst.info("Restoring %s from backup" % self.filepath)

        if not self.enabled:
            loggerinst.info("%s hasn't been backed up." % self.filepath)
            return

        # Possible exceptions will be handled in the BackupController
        shutil.copy2(self.backup_path, self.filepath)
        if rollback:
            # Remove the backed up file only when processing rollback
            os.remove(self.backup_path)

        if rollback:
            loggerinst.info("File %s restored." % self.filepath)
            super(RestorableFile, self).restore()
        else:
            loggerinst.debug("File %s restored." % self.filepath)
            # not setting enabled to false since this is not being rollback
            # restoring the backed up file for conversion purposes

    def remove(self):
        """Remove restored file from original place, backup isn't removed"""
        try:
            os.remove(self.filepath)
            loggerinst.debug("File %s removed." % self.filepath)
        except (OSError, IOError):
            loggerinst.debug("Couldn't remove restored file %s" % self.filepath)

    def __eq__(self, value):
        if hash(self) == hash(value):
            return True
        return False

    def __hash__(self):
        return hash(self.filepath) if self.filepath else super(RestorableFile, self).__hash__()


class MissingFile(RestorableChange):
    """
    File not present before conversion. Could be created during
    conversion so should be removed in rollback.
    """

    def __init__(self, filepath):
        super(MissingFile, self).__init__()
        self.filepath = filepath

    def enable(self):
        if self.enabled:
            return

        if os.path.isfile(self.filepath):
            loggerinst.debug(
                "The file {filepath} is present on the system before conversion, skipping it.".format(
                    filepath=self.filepath
                )
            )
            return

        loggerinst.info("Marking file {filepath} as missing on system.".format(filepath=self.filepath))
        super(MissingFile, self).enable()

    def restore(self):
        """Remove the file if it was created during conversion.

        .. warning::
            Exceptions are not handled and left for handling by the calling code.

        :raises OSError: When the removal of the file fails.
        :raises IOError: When the removal of the file fails.
        """
        if not self.enabled:
            return

        loggerinst.task("Rollback: Remove file created during conversion {filepath}".format(filepath=self.filepath))

        if not os.path.isfile(self.filepath):
            loggerinst.info("File {filepath} wasn't created during conversion".format(filepath=self.filepath))
        else:
            # Possible exceptions will be handled in the BackupController
            os.remove(self.filepath)
            loggerinst.info("File {filepath} removed".format(filepath=self.filepath))

            super(MissingFile, self).restore()
