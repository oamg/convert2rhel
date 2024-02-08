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
import logging
import os

import six

from convert2rhel.utils import TMP_DIR


#: Directory for temporary backing up files, packages and other relevant stuff.
BACKUP_DIR = os.path.join(TMP_DIR, "backup")

loggerinst = logging.getLogger(__name__)


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

    # Sentinel value.  If this is pushed onto the BackupController, then when
    # pop_to_partition() is called, it will only pop until it reaches
    # a partition in the list.
    # Only one pop_to_partition() will make use of the partitions. All other
    # methods will discard them.
    partition = object()

    def __init__(self):
        self._restorables = []

    def push(self, restorable):
        """
        Enable a RestorableChange and track it in case it needs to be restored.

        :arg restorable: RestorableChange object that can be restored later.
        """
        # This is part of a hack for 1.4 that allows us to only pop some of
        # the registered changes.  Remove it when all of the rollback items have
        # been ported into the backup controller.
        if restorable is self.partition:
            self._restorables.append(restorable)
            return

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

        # Ignore the 1.4 partition hack
        if restorable is self.partition:
            return self.pop()

        restorable.restore()

        return restorable

    def pop_all(self, _honor_partitions=False):
        """
        Restores all RestorableChanges known to the Controller and then returns them.

        :returns: List of RestorableChange objects that were known to the Controller.
        :raises IndexError: If there are no RestorableChanges currently known to the Controller.

        After running, the Controller object will not know about any RestorableChanges.

        .. note:: _honor_partitions is part of a hack for 1.4 to let us split restoring changes into
            two parts.  During rollback, the part before the partition is restored before the legacy
            backups.  Then the remainder of the changes managed by BackupController are restored.
            This can go away once we merge all of the legacy backups into RestorableChanges managed
            by BackupController.

            .. seealso:: Jira ticket to track porting to BackupController: https://issues.redhat.com/browse/RHELC-1153
        """
        # Only raise IndexError if there are no restorables registered.
        # Partitions are ignored for this check as they aren't really Changes.
        if not self._restorables or all(r == self.partition for r in self._restorables):
            raise IndexError("No backups to restore")

        # Restore the Changes in the reverse order the changes were enabled.
        processed_restorables = []
        while True:
            try:
                restorable = self._restorables.pop()
            except IndexError:
                break

            if restorable is self.partition:
                if _honor_partitions:
                    # Stop once a partition is reached (this is how
                    # pop_to_partition() is implemented.
                    return []
                else:
                    # This code ignores partitions.  Only pop_to_partition() honors
                    # them.
                    continue

            try:
                restorable.restore()
            # Catch SystemExit too because we might still be calling
            # logger.critical in some places.
            except (Exception, SystemExit) as e:
                # Don't let a failure in one restore influence the others
                loggerinst.warning("Error while rolling back a %s: %s" % (restorable.__class__.__name__, str(e)))

            processed_restorables.append(restorable)

        return processed_restorables

    def pop_to_partition(self):
        """
        This is part of a hack to get 1.4 out the door.  It should be removed once all rollback
        items are ported into the backup controller framework.

        Calling this method will pop and restore changes until a partition is reached.  When that
        happens, it will return.  To restore everything, first call this method and then call pop_all().

        .. warning::
            * For the hack to 1.4, you need to make sure that at least one partition has been pushed
                onto the stack.
            * Unlike pop() and pop_all(), this method doesn't return anything.
        """
        self.pop_all(_honor_partitions=True)


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
