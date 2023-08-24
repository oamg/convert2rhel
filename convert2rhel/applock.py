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

import errno
import io
import logging
import os
import tempfile


_DEFAULT_LOCK_DIR = "/var/lock/run"
loggerinst = logging.getLogger(__name__)


class ApplicationLockedError(Exception):
    """Raised when this application is locked."""

    def __init__(self, message):
        super(ApplicationLockedError, self).__init__(message)
        self.message = message


class ApplicationLock(object):
    """Holds a lock for a particular application.

    To acquire and release the lock, we recommend using the context
    manager, though trylock() and unlock() methods are provided. You
    may call unlock() without having called trylock() first, so it
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
        # Maximum number of tries to lock
        self._max_loop_count = 5
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
        #
        # Create a temporary file that contains our PID and attempt
        # to link it to the real pidfile location. The link will fail if
        # the file already exists; this avoids a race condition when
        # two processes attempt to create the file simultaneously. This
        # also guarantees that the lock file contains valid data.
        #
        with tempfile.NamedTemporaryFile(mode="wt", suffix=".pid", prefix=self._name, dir=_DEFAULT_LOCK_DIR) as fileh:
            fileh.write(str(self._pid) + "\n")
            fileh.flush()
            try:
                os.link(fileh.name, self._pidfile)
            # In Python 3 this could be changed to catch FileExistsError.
            except OSError as exc:
                if exc.errno == errno.EEXIST:
                    return False
                raise exc
        loggerinst.debug("%s." % self)
        return True

    @property
    def is_locked(self):
        """Test whether this object is locked."""
        return self._locked

    @staticmethod
    def _pid_exists(pid):
        """Test whether a particular process exists."""
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def trylock(self, loop_count=0):
        """Try to get a lock on this application. If successful,
        the application will be locked; the lock should be released
        with unlock().

        If the file has unexpected contents, for safety we treat the
        application as locked, since it is probably the result of
        manual meddling, intentional or otherwise.

        Note that nothing prevents you from calling trylock()
        multiple times; all calls after the first will fail as if
        another process holds the lock.

        :param loop_count: used internally to limit the number of
                           recursive calls to this method
        :raises ApplicationLockedError: the application is locked
        """
        if loop_count > self._max_loop_count:
            raise ApplicationLockedError("Cannot lock %s" % self._pidfile)
        if self._try_create():
            self._locked = True
            return

        with io.open(self._pidfile, "rt") as fileh:
            file_contents = fileh.read()
            try:
                pid = int(file_contents.rstrip())
            except ValueError:
                raise ApplicationLockedError("Lock file %s is corrupt" % self._name)

        if self._pid_exists(pid):
            raise ApplicationLockedError("%s locked by process %d" % (self._name, pid))
        else:
            #
            # The lock file was created by a process that has exited;
            # remove it and try again.
            #
            loggerinst.info("Reaping lock held by process %d." % pid)
            try:
                os.unlink(self._pidfile)
            except OSError:
                loggerinst.warning("Couldn't unlink %s." % self.pidfile)
            self.trylock(loop_count + 1)

    def unlock(self):
        """Release the lock on this application."""
        if self._locked == False:
            return
        try:
            os.unlink(self._pidfile)
        except OSError:
            loggerinst.warning("Couldn't unlink %s." % self._pidfile)
        loggerinst.debug("%s." % self)
        self._locked = False

    def __enter__(self):
        self.trylock()
        return self

    def __exit__(self, _type, _value, _tb):
        self.unlock()
