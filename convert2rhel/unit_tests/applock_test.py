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

import os
import subprocess

import pytest

from convert2rhel import applock


@pytest.fixture
def tmp_lock():
    alock = applock.ApplicationLock("convert2rhelTEST", lock_dir="/tmp")
    return alock


def test_applock_context_manager():
    pidfile = "/non/existent/file"
    with applock.ApplicationLock("convert2rhelTEST", lock_dir="/tmp") as tmp_lock:
        pidfile = tmp_lock._pidfile
        assert tmp_lock.is_locked is True
        assert os.path.isfile(pidfile) is True
    assert os.path.isfile(pidfile) is False


def test_applock_basic(tmp_lock):
    tmp_lock.trylock()
    assert tmp_lock.is_locked is True
    assert os.path.isfile(tmp_lock._pidfile) is True
    tmp_lock.unlock()
    assert tmp_lock.is_locked is False
    assert os.path.isfile(tmp_lock._pidfile) is False


def test_applock_basic_islocked(tmp_lock):
    with open(tmp_lock._pidfile, "w") as fileh:
        pid = os.getpid()
        fileh.write(str(pid) + "\n")
    with pytest.raises(applock.ApplicationLockedError):
        tmp_lock.trylock()
    os.unlink(tmp_lock._pidfile)


def test_applock_basic_reap(tmp_lock):
    """Test the case where the lockfile was held by a process
    that has exited."""
    old_pid = subprocess.check_output("/bin/echo $$", shell=True, universal_newlines=True)
    with open(tmp_lock._pidfile, "w") as fileh:
        fileh.write(old_pid)
    tmp_lock.trylock()
    os.unlink(tmp_lock._pidfile)


def test_applock_basic_byzantine1(tmp_lock):
    """Test the case where the lock file exists, but has bogus data."""
    with open(tmp_lock._pidfile, "w") as fileh:
        fileh.write("This is bogus data.")
    with pytest.raises(applock.ApplicationLockedError):
        tmp_lock.trylock()
    os.unlink(tmp_lock._pidfile)


def test_applock_basic_byzantine2(tmp_lock):
    """Test the case where the lock file exists, but is empty."""
    with open(tmp_lock._pidfile, "w") as fileh:
        pass
    with pytest.raises(applock.ApplicationLockedError):
        tmp_lock.trylock()
    os.unlink(tmp_lock._pidfile)


def test_applock_basic_byzantine3(tmp_lock):
    """Test the case where the lock file exists, but we can't read it."""
    with open(tmp_lock._pidfile, "w") as fileh:
        pid = os.getpid()
        fileh.write(str(pid) + "\n")
    os.chmod(tmp_lock._pidfile, 0)
    with pytest.raises(IOError):
        tmp_lock.trylock()
    os.unlink(tmp_lock._pidfile)
