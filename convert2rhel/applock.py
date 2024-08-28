# -*- coding: utf-8 -*-
#
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

import errno
import logging
import os
import stat
import tempfile


_DEFAULT_LOCK_DIR = "/var/run/lock"
loggerinst = logging.getLogger(__name__)


class ApplicationLockedError(Exception):
    """Raised when this application is already locked."""

    def __init__(self, message):
        super(ApplicationLockedError, self).__init__(message)
        self.message = message


class ApplicationLock:
    """Holds a lock for a particular application.

    To acquire and release the lock, we recommend using the context
    manager, though try_to_lock() and unlock() methods are provided. You
    may call unlock() without having called try_to_lock() first, so it
    can be used in a cleanup routine without worries.

    The implementation uses a standard Linux PID file. When a program
    that uses ApplicationLock starts, it writes its process ID to a
    file in /var/run/lock. If the file already exists, it reads and
    reports the PID that it finds.

    While it would be nice to try to clean up a stale process ID file
    (i.e., a file created by a process that has exited) that opens up
    a race condition that would require us to leave the process ID
    file pointer open across the invocation of several methods, which
    would complicate the code more than the feature is worth.

    For safety, unexpected conditions, like garbage in the file or
    bad permissions, are treated as if the application is locked,
    because something is obviously wrong.
    """

    def __init__(self, name):
        # Our application name
        self._name = name
        # Our process ID. We save this when the lock is created so it will be
        # consistent even if we check from inside a fork.
        self._pid = os.getpid()
        # Path to the file that contains the process id
        self._pidfile = os.path.join(_DEFAULT_LOCK_DIR, self._name + ".pid")

    def __str__(self):
        if self.is_locked:
            status = "locked"
        else:
            status = "unlocked"
        return "%s PID %d %s" % (self._pidfile, self._pid, status)

    def _try_create(self):
        """Try to create the lock file. If this succeeds, the lock
        file exists and we created it, so we hold the lock. If an
        exception other than the one we expect is raised, re-raises
        it.

        :returns: True if we created the lock, False if we didn't.
        """
        # Create a temporary file that contains our PID and attempt
        # to link it to the real pidfile location. The link will fail if
        # the file already exists; this avoids a race condition when
        # two processes attempt to create the file simultaneously. This
        # also guarantees that the lock file contains valid data.
        #
        # Note that NamedTemporaryFile will clean up the file it created,
        # but the lockfile we created by doing the link will stay around.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pid", prefix=self._name, dir=_DEFAULT_LOCK_DIR) as f:
            # stat.S_IRUSR = Owner has read permission
            # stat.S_IWUSR = Owner has write permission
            os.chmod(f.name, stat.S_IRUSR | stat.S_IWUSR)
            f.write(str(self._pid) + "\n")
            f.flush()
            try:
                os.link(f.name, self._pidfile)
            # In Python 3 this could be changed to catch FileExistsError.
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    return False
                raise
        loggerinst.debug("%s." % self)
        return True

    def _get_pid_from_file(self):
        """If the lock file exists, return the process ID stored in
        the file. No check is made whether the process exists. Because
        of the way we create the lock file, the case where it has bad
        data or is empty is a pathological case.

        :returns: The process ID, or None if the file does not exist.
        :raises ApplicationLockedError: Bad data in the file.
        """
        try:
            with open(self._pidfile, "r") as filep:
                file_contents = filep.read()
                pid = int(file_contents.rstrip())
                if pid:
                    return pid
        except ValueError:
            raise ApplicationLockedError("%s has invalid contents" % (self._pidfile))
        except (IOError, OSError) as exc:
            if exc.errno == errno.ENOENT:
                return None
            raise
        return None

    @property
    def is_locked(self):
        """Test whether this object was locked by this instance of
        the application."""
        pid = self._get_pid_from_file()
        return pid == self._pid

    def _safe_unlink(self):
        """Unlink the lock file. If the unlink fails because the file
        doesn't exist, swallow the exception; this avoids spurious
        errors due to race conditions.
        """
        try:
            os.unlink(self._pidfile)
        except OSError as exc:
            # In Python 3 this could be changed to FileNotFoundError.
            if exc.errno == errno.ENOENT:
                return
            raise

    def try_to_lock(self):
        """Try to get a lock on this application. If this method does
        not raise an Exception, the application will be locked and we
        hold the lock; the lock should be released with unlock().

        If the file has unexpected contents, for safety we treat the
        application as locked, since it is probably the result of
        manual meddling, intentional or otherwise.

        :raises ApplicationLockedError: the application is locked
        """
        if self._try_create():
            return
        pid = self._get_pid_from_file()
        if pid == self._pid:
            return
        raise ApplicationLockedError("%s locked by process %d" % (self._pidfile, pid))

    def unlock(self):
        """Release the lock on this application.

        Note that if the safe unlink fails (a pathological failure)
        the object will stay locked and the OSError or other
        system-generated exception will be raised.
        """
        if not self.is_locked:
            return
        self._safe_unlink()
        loggerinst.debug("%s." % self)

    def __enter__(self):
        self.try_to_lock()
        return self

    def __exit__(self, _type, _value, _tb):
        self.unlock()
