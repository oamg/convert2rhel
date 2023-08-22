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

import atexit
import errno
import io
import logging
import os
import time


loggerinst = logging.getLogger(__name__)


class ApplicationLockedError(Exception):
    """Raised when this application is locked."""

    def __init__(self, message):
        super(ApplicationLockedError, self).__init__(message)
        self.message = message


class ApplicationLock(object):
    """Holds a lock for a particular application.

    The implementation uses a standard Linux PID file, though that
    fact (and all implementation details) are hidden from the caller.
    To acquire and release the lock, use trylock() and unlock().
    """

    def __init__(self, name):
        # Our application name
        self._name = name
        # Directory in which the lockfile will be written
        self._lock_dir = "/var/run/lock"
        # Do we think we locked the pid file?
        self._locked = False
        # Maximum number of tries to lock
        self._max_loop_count = 5
        # Our process ID
        self._pid = os.getpid()
        # Path to the file that contains the process id
        self._pidfile = os.path.join(self._lock_dir, self._name + ".pid")

    def __str__(self):
        if self._locked:
            status = "locked"
        else:
            status = "unlocked"
        return "%s PID %d %s" % (self._pidfile, self._pid, status)

    def set_lock_dir(self, new_tmp_dir):
        """Set the lock directory. Used only for testing.

        :param new_tmp_dir: the directory to be used for the lock file
        """
        self._lock_dir = new_tmp_dir
        self._pidfile = os.path.join(self._lock_dir, self._name + ".pid")

    def _try_creat(self):
        """Try to create the lock file. If this succeeds, the lock file
        exists and we created it.

        :returns: True if we created the lock, False if we didn't.
        """
        try:
            file_desc = os.open(self._pidfile, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o755)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                return False
            raise exc
        encoded = (str(self._pid) + "\n").encode("ascii")
        os.write(file_desc, encoded)
        os.close(file_desc)
        loggerinst.debug("%s." % self)
        return True

    def is_locked(self):
        """Test whether this object is locked."""
        return self._locked

    @staticmethod
    def _pid_exists(pid):
        """Test whether a particular process exists."""
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        return True

    def trylock(self, loop_count=0):
        """Try to get a lock on this application. If successful,
        the application will be locked; the lock may be released
        with trylock() or it will be cleaned up automatically at
        process exit.

        Note that nothing prevents you from calling trylock()
        multiple times; all calls after the first will fail as if
        another process holds the lock.

        :raises ApplicationLockedError: the application is locked
        """
        if loop_count > self._max_loop_count:
            raise ApplicationLockedError("Cannot lock %s" % self._pidfile)
        if self._try_creat():
            self._locked = True
            atexit.register(self.unlock)
            return

        with io.open(self._pidfile, "rt") as fileh:
            try:
                file_contents = fileh.read()
                pid = int(file_contents.rstrip())
                if file_contents[-1] != "\n" or pid == 0:
                    raise ValueError("Bogus file contents")
            except (OSError, ValueError):
                #
                # Two possibilities here: either the file is corrupt
                # or another process hasn't finished writing it out.
                # The sleep(0) is just a cheap way to let another
                # process run without making us wait too long if the
                # file really is corrupt.
                #
                time.sleep(0)
                self.trylock(loop_count + 1)

        if self._pid_exists(pid):
            raise ApplicationLockedError("%s locked by process %d" % (self._name, pid))
        else:
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
        # Call this in Python 3?
        # atexit.unregister(self.unlock)
        loggerinst.debug("%s." % self)
        self._locked = False

    def __enter__(self):
        self.trylock()
        return self

    def __exit__(self, _type, _value, _tb):
        self.unlock()
