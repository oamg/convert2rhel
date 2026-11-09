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


import hashlib
import os
import shutil

from convert2rhel import exceptions
from convert2rhel.backup import BACKUP_DIR, RestorableChange
from convert2rhel.logger import root_logger

logger = root_logger.getChild(__name__)


class RestorableFile(RestorableChange):
    def __init__(self, filepath):
        super().__init__()
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

        logger.info(f"Backing up {self.filepath}.")
        if os.path.isfile(self.filepath):
            try:
                backup_path = self._hash_backup_path()
                self.backup_path = backup_path
                shutil.copy2(self.filepath, backup_path)
                logger.debug(f"Copied {self.filepath} to {backup_path}.")
            except OSError as err:
                # IOError for py2 and OSError for py3
                logger.critical_no_exit(f"Error({err.errno}): {err.strerror}")
                raise exceptions.CriticalError(
                    id_="FAILED_TO_SAVE_FILE_TO_BACKUP_DIR",
                    title="Failed to copy file to the backup directory.",
                    description=(
                        "Copying the current file has failed. This can lead to inconsistency during the rollbacks as "
                        "convert2rhel won't be able to restore the file in case of failures."
                        "In the current case, we encountered a failure while performing that backup so it is unsafe "
                        "to continue. See the diagnosis section to identify which problem ocurred during the backup."
                    ),
                    diagnosis=f"Failed to backup {self.filepath}. Errno: {err.errno}, Error: {err.strerror}",
                )
        else:
            logger.info("Can't find %s.", self.filepath)
            return

        # Set the enabled value
        super().enable()

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
            logger.task(f"Restore {self.filepath} from backup")
        else:
            logger.info(f"Restoring {self.filepath} from backup")

        if not self.enabled:
            logger.info(f"{self.filepath} hasn't been backed up.")
            return

        # Possible exceptions will be handled in the BackupController
        shutil.copy2(self.backup_path, self.filepath)
        if rollback:
            # Remove the backed up file only when processing rollback
            os.remove(self.backup_path)

        if rollback:
            logger.info(f"File {self.filepath} restored.")
            super().restore()
        else:
            logger.debug(f"File {self.filepath} restored.")
            # not setting enabled to false since this is not being rollback
            # restoring the backed up file for conversion purposes

    def remove(self):
        """Remove restored file from original place, backup isn't removed"""
        try:
            os.remove(self.filepath)
            logger.debug(f"File {self.filepath} removed.")
        except OSError:
            logger.debug(f"Couldn't remove restored file {self.filepath}")

    def __eq__(self, value):
        if hash(self) == hash(value):
            return True
        return False

    def __hash__(self):
        return hash(self.filepath) if self.filepath else super().__hash__()


class MissingFile(RestorableChange):
    """
    File not present before conversion. Could be created during
    conversion so should be removed in rollback.
    """

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def enable(self):
        if self.enabled:
            return

        if os.path.isfile(self.filepath):
            logger.debug(f"The file {self.filepath} is present on the system before conversion, skipping it.")
            return

        logger.info(f"Marking file {self.filepath} as missing on system.")
        super().enable()

    def restore(self):
        """Remove the file if it was created during conversion.

        .. warning::
            Exceptions are not handled and left for handling by the calling code.

        :raises OSError: When the removal of the file fails.
        :raises IOError: When the removal of the file fails.
        """
        if not self.enabled:
            return

        logger.task(f"Remove file created during conversion {self.filepath}")

        if not os.path.isfile(self.filepath):
            logger.info(f"File {self.filepath} wasn't created during conversion")
        else:
            # Possible exceptions will be handled in the BackupController
            os.remove(self.filepath)
            logger.info(f"File {self.filepath} removed")

            super().restore()


class InstalledFile(RestorableChange):
    """
    A file we plant on the system during the conversion. It can either be removed on a rollback or after a successful
    conversion, depending on what purpose the planted file serves.
    """

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def enable(self):
        if self.enabled:
            return

        logger.info(f"Marking file {self.filepath} as installed on the system.")
        super().enable()

    def restore(self):
        """Remove the file if it was installed during the conversion.

        .. warning::
            Exceptions are not handled and left for handling by the calling code.

        :raises OSError: When the removal of the file fails.
        :raises IOError: When the removal of the file fails.
        """
        if not self.enabled:
            return

        logger.task(f"Remove {self.filepath} installed during the conversion")

        if not os.path.isfile(self.filepath):
            logger.info(f"File {self.filepath} wasn't installed during conversion.")
        else:
            # Possible exceptions will be handled in the BackupController
            os.remove(self.filepath)
            logger.info(f"File {self.filepath} removed.")

            super().restore()
