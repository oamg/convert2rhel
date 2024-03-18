# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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

import abc
import hashlib
import logging
import os

import six

from convert2rhel.repo import DEFAULT_YUM_REPOFILE_DIR
from convert2rhel.utils import TMP_DIR


# Directory for temporary backing up files, packages and other relevant stuff.
BACKUP_DIR = os.path.join(TMP_DIR, "backup")

loggerinst = logging.getLogger(__name__)


def get_backedup_system_repos():
    """Get the backedup system repos path inside our backup structure.

    :returns str: A formatted backedup path for system repositories
    """
    backedup_reposdir = os.path.join(BACKUP_DIR, hashlib.md5(DEFAULT_YUM_REPOFILE_DIR.encode()).hexdigest())
    return backedup_reposdir


class BackupController:
    """
    Controls backup and restore for all restorable types.

    This is the second version of a backup controller.  It handles all types of
    things that convert2rhel will change on the system which it can restore in
    case of a failure before the Point-of-no-return (PONR).

    The basic interface to this is a LIFO stack.  When a Restorable is pushed
    onto the stack, it is backed up.  When it is popped off of the stack, it is
    restored.  Changes are restored in the reverse order that that they were
    added.  Changes cannot be retrieved and restored out of order.
    """

    def __init__(self):
        self._restorables = []
        self._rollback_failures = []

    def push(self, restorable):
        """
        Enable a RestorableChange and track it in case it needs to be restored.

        :arg restorable: RestorableChange object that can be restored later.
        """
        if not isinstance(restorable, RestorableChange):
            raise TypeError("`%s` is not a RestorableChange object" % restorable)

        restorable.enable()

        self._restorables.append(restorable)

    def pop(self):
        """
        Restore and then return the last RestorableChange added to the Controller.

        :returns: RestorableChange object that was last added.
        :raises IndexError: If there are no RestorableChanges currently known to the Controller.
        """
        try:
            restorable = self._restorables.pop()
        except IndexError as e:
            # Use a more specific error message
            args = list(e.args)
            args[0] = "No backups to restore"
            e.args = tuple(args)
            raise e

        restorable.restore()

        return restorable

    def pop_all(self):
        """
        Restores all RestorableChanges known to the Controller and then returns them.

        :returns list[RestorableChange]: List of RestorableChange objects that were processed by the Controller.
        :raises IndexError: If there are no RestorableChanges currently known to the Controller.

        After running, the Controller object will not know about any RestorableChanges.
        """
        # Only raise IndexError if there are no restorables registered.
        if not self._restorables:
            raise IndexError("No backups to restore")

        processed_restorables = []

        # Restore the Changes in the reverse order the changes were enabled.
        while True:
            try:
                restorable = self._restorables.pop()
            except IndexError:
                break

            try:
                restorable.restore()
            # Catch SystemExit too because we might still be calling
            # logger.critical in some places.
            except (Exception, SystemExit) as e:
                # Don't let a failure in one restore influence the others
                message = "Error while rolling back a %s: %s" % (restorable.__class__.__name__, str(e))
                loggerinst.warning(message)
                # Add the rollback failures to the list
                self._rollback_failures.append(message)

            processed_restorables.append(restorable)

        return processed_restorables

    @property
    def rollback_failed(self):
        """
        Return True when one or more restorables were unsuccessful.

        :returns: bool True if the rollback failed, False if rollback succeeded.
        """

        return any(self._rollback_failures)

    @property
    def rollback_failures(self):
        """
        Errors from failed rollback. Used to provide more information to the user.

        :returns: List of strings containing errors captured during rollback.
        """
        return self._rollback_failures


@six.add_metaclass(abc.ABCMeta)
class RestorableChange:
    """
    Interface definition for types which can be restored.
    """

    @abc.abstractmethod
    def __init__(self):
        self.enabled = False

    @abc.abstractmethod
    def enable(self):
        """
        Backup should be idempotent.  In other words, it should know if the resource has already
        been backed up and refuse to do so a second time.
        """
        self.enabled = True

    @abc.abstractmethod
    def restore(self):
        """
        Restore the state of the system.
        """
        self.enabled = False


backup_control = BackupController()
