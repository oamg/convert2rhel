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

import logging
import os
import shutil

from convert2rhel import exceptions
from convert2rhel.backup import RestorableChange
from convert2rhel.utils import BACKUP_DIR


loggerinst = logging.getLogger(__name__)


class RestorableFile(RestorableChange):
    def __init__(self, filepath):
        super(RestorableFile, self).__init__()
        self.filepath = filepath

    def enable(self):
        """Save current version of a file"""
        # Prevent multiple backup
        if self.enabled:
            return

        loggerinst.info("Backing up %s." % self.filepath)
        if os.path.isfile(self.filepath):
            try:
                shutil.copy2(self.filepath, BACKUP_DIR)
                loggerinst.debug("Copied %s to %s." % (self.filepath, BACKUP_DIR))
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

        # Set the enabled value
        super(RestorableFile, self).enable()

    def restore(self, rollback=True):
        """Restore a previously backed up file"""
        if rollback:
            loggerinst.task("Rollback: Restore %s from backup" % self.filepath)
        else:
            loggerinst.info("Restoring %s from backup" % self.filepath)

        backup_filepath = os.path.join(BACKUP_DIR, os.path.basename(self.filepath))

        # We do not have backup or not backed up by this
        if not self.enabled or not os.path.isfile(backup_filepath):
            loggerinst.info("%s hasn't been backed up." % self.filepath)
            return

        try:
            shutil.copy2(backup_filepath, self.filepath)
        except (OSError, IOError) as err:
            # Do not call 'critical' which would halt the program. We are in
            # a rollback phase now and we want to rollback as much as possible.
            # IOError for py2 and OSError for py3
            loggerinst.critical_no_exit("Error(%s): %s" % (err.errno, err.strerror))
            return

        if rollback:
            loggerinst.info("File %s restored." % self.filepath)
            super(RestorableFile, self).restore()
        else:
            loggerinst.debug("File %s restored." % self.filepath)
            # not setting enabled to false since this is not being rollback
            # restoring the backed up file for conversion purposes

    # Probably will be deprecated and unusable since using the BackupController
    # Depends on specific usage of this
    def remove(self):
        """Remove restored file from original place, backup isn't removed"""
        try:
            os.remove(self.filepath)
            loggerinst.debug("File %s removed." % self.filepath)
        except (OSError, IOError):
            loggerinst.debug("Couldn't remove restored file %s" % self.filepath)


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
        if not self.enabled:
            return

        loggerinst.task("Rollback: remove file created during conversion {filepath}".format(filepath=self.filepath))

        if not os.path.isfile(self.filepath):
            loggerinst.info("File {filepath} wasn't created during conversion".format(filepath=self.filepath))
        else:
            try:
                os.remove(self.filepath)
                loggerinst.info("File {filepath} removed".format(filepath=self.filepath))
            except OSError as err:
                # Do not call 'critical' which would halt the program. We are in
                # a rollback phase now and we want to rollback as much as possible.
                loggerinst.critical_no_exit("Error(%s): %s" % (err.errno, err.strerror))
                return

        super(MissingFile, self).restore()
