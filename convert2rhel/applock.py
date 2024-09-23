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
import os
import tempfile

from convert2rhel.logger import root_logger


_DEFAULT_LOCK_DIR = "/var/run/lock"
logger = root_logger.getChild(__name__)


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
    file in /var/run/lock. If the file already exists, it reads the
    PID and checks to see if the process is still running. If the
    process is still running, it raises ApplicationLockedError. If the
    process is not running, it removes the file and tries to lock it
    again.

    For safety, unexpected conditions, like garbage in the file or
    bad permissions, are treated as if the application is locked,
    because something is obviously wrong.
    """

    def __init__(self, name):
        # Our application name
        self._name = name
        # Do we think we locked the pid file?
        self._locked = False
        # Our process ID
        self._pid = os.getpid()
        # Path to the file that contains the process id
        self._pidfile = os.path.join(_DEFAULT_LOCK_DIR, self._name + ".pid")

    def __str__(self):
        if self._locked:
            status = "locked"
        else:
            status = "unlocked"
        return "%s PID %d %s" % (self._pidfile, self._pid, status)

    def _try_create(self):
        """Try to create the lock file. If this succeeds, the lock file
        exists and we created it. If an exception other than the one
        we expect is raised, re-raises it.

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
            f.write(str(self._pid) + "\n")
            f.flush()
            try:
                os.link(f.name, self._pidfile)
            # In Python 3 this could be changed to catch FileExistsError.
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    return False
                raise exc
        logger.debug("{}.".format(self))
        return True

    @property
    def is_locked(self):
        """Test whether this object is locked."""
        return self._locked

    @staticmethod
    def _pid_exists(pid):
        """Test whether a particular process exists."""
        try:
            # Bulletproofing: avoid killing init or all processes.
            if pid > 1:
                os.kill(pid, 0)
        except OSError as exc:
            # The only other (theoretical) possibility is EPERM, which
            # would mean the process exists.
            if exc.errno == errno.ESRCH:
                return False
        return True

    def try_to_lock(self, _recursive=False):
        """Try to get a lock on this application. If successful,
        the application will be locked; the lock should be released
        with unlock().

        If the file has unexpected contents, for safety we treat the
        application as locked, since it is probably the result of
        manual meddling, intentional or otherwise.

        :keyword _recursive: True if we are being called recursively
                             and should not try to clean up the lockfile
                             again.
        :raises ApplicationLockedError: the application is locked
        """
        if self._try_create():
            self._locked = True
            return
        if _recursive:
            raise ApplicationLockedError("Cannot lock {}".format(self._name))

        with open(self._pidfile, "r") as f:
            file_contents = f.read()
        try:
            pid = int(file_contents.rstrip())
        except ValueError:
            raise ApplicationLockedError("Lock file {} is corrupt".format(self._pidfile))

        if self._pid_exists(pid):
            raise ApplicationLockedError("%s locked by process %d" % (self._pidfile, pid))
        # The lock file was created by a process that has exited;
        # remove it and try again.
        logger.info("Cleaning up lock held by exited process %d." % pid)
        os.unlink(self._pidfile)
        self.try_to_lock(_recursive=True)

    def unlock(self):
        """Release the lock on this application.

        Note that if the unlink fails (a pathological failure) the
        object will stay locked and the OSError or other
        system-generated exception will be raised.
        """
        if not self._locked:
            return
        os.unlink(self._pidfile)
        self._locked = False
        logger.debug("{}.".format(self))

    def __enter__(self):
        self.try_to_lock()
        return self

    def __exit__(self, _type, _value, _tb):
        self.unlock()
