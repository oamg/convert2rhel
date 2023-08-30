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
def tmp_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
    alock = applock.ApplicationLock("convert2rhelTEST")
    return alock


def test_applock_context_manager(monkeypatch, tmp_path):
    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
    with applock.ApplicationLock("convert2rhelTEST") as tmp_lock:
        pidfile = tmp_lock._pidfile
        assert tmp_lock.is_locked is True
        assert os.path.isfile(pidfile) is True
    assert os.path.isfile(pidfile) is False


def test_applock_basic(tmp_lock):
    tmp_lock.try_to_lock()
    assert tmp_lock.is_locked is True
    assert os.path.isfile(tmp_lock._pidfile) is True
    tmp_lock.unlock()
    assert tmp_lock.is_locked is False
    assert os.path.isfile(tmp_lock._pidfile) is False


def test_applock_basic_islocked(tmp_lock):
    with open(tmp_lock._pidfile, "w") as f:
        pid = os.getpid()
        f.write(str(pid) + "\n")
    with pytest.raises(applock.ApplicationLockedError):
        tmp_lock.try_to_lock()
    os.unlink(tmp_lock._pidfile)


def test_applock_basic_reap(tmp_lock):
    """Test the case where the lockfile was held by a process
    that has exited."""
    old_pid = subprocess.check_output("/bin/echo $$", shell=True, universal_newlines=True)
    with open(tmp_lock._pidfile, "w") as f:
        f.write(old_pid)
    tmp_lock.try_to_lock()
    os.unlink(tmp_lock._pidfile)


def test_applock_bogus_lock(tmp_lock):
    """Test the case where the lock file exists, but has bogus data."""
    with open(tmp_lock._pidfile, "w") as f:
        f.write("This is bogus data.")
    with pytest.raises(applock.ApplicationLockedError):
        tmp_lock.try_to_lock()
    os.unlink(tmp_lock._pidfile)


def test_applock_empty_lock(tmp_lock):
    """Test the case where the lock file exists, but is empty."""
    with open(tmp_lock._pidfile, "w"):
        pass
    with pytest.raises(applock.ApplicationLockedError):
        tmp_lock.try_to_lock()
    os.unlink(tmp_lock._pidfile)


def test_applock_cant_read_lock(tmp_lock):
    """Test the case where the lock file exists, but we can't read it."""
    with open(tmp_lock._pidfile, "w") as f:
        pid = os.getpid()
        f.write(str(pid) + "\n")
    os.chmod(tmp_lock._pidfile, 0)
    with pytest.raises(IOError):
        tmp_lock.try_to_lock()
    os.unlink(tmp_lock._pidfile)


def test_applock_link_fails(tmp_lock):
    """Test the case where the os.link call to create the lockfile
    fails, but not because the file exists."""
    dir = os.path.dirname(tmp_lock._pidfile)
    os.chmod(dir, 0o550)
    with pytest.raises(OSError):
        tmp_lock.try_to_lock()
    assert tmp_lock.is_locked is False
    os.chmod(dir, 0o750)


def test_applock_lock_unlink_fails(tmp_lock):
    """Test the case where we can't unlink a bad pid file."""
    old_pid = subprocess.check_output("/bin/echo $$", shell=True, universal_newlines=True)
    with open(tmp_lock._pidfile, "w") as f:
        f.write(old_pid)
    dir = os.path.dirname(tmp_lock._pidfile)
    os.chmod(dir, 0o550)
    with pytest.raises(OSError):
        tmp_lock.try_to_lock()
    os.chmod(dir, 0o750)
    os.unlink(tmp_lock._pidfile)


def test_applock_unlock_without_lock(tmp_lock):
    """Test unlocking without locking first."""
    assert tmp_lock.is_locked is False
    tmp_lock.unlock()
    assert tmp_lock.is_locked is False
    assert os.path.isfile(tmp_lock._pidfile) is False
