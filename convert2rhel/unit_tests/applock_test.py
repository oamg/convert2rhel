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
import pytest

from convert2rhel import applock

def test_applock_basic():
    alock = applock.ApplicationLock("convert2rhelTEST")
    alock.set_lock_dir("/tmp")
    alock.trylock()
    assert alock.is_locked() is True
    assert os.path.isfile(alock._pidfile) is True
    alock.unlock()
    assert alock.is_locked() is False
    assert os.path.isfile(alock._pidfile) is False

def test_applock_basic_islocked():
    alock = applock.ApplicationLock("convert2rhelTEST")
    alock.set_lock_dir("/tmp")
    with open(alock._pidfile, "w") as fileh:
        pid = os.getpid()
        fileh.write(str(pid) + '\n')
    saw_exception = False
    try:
        alock.trylock()
    except applock.ApplicationLockedError:
        saw_exception = True
    finally:
        os.unlink(alock._pidfile)
    assert saw_exception == True

