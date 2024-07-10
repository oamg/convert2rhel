# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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

import pytest
import six

from convert2rhel import checks
from convert2rhel.unit_tests import RunSubprocessMocked
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    ("latest_installed_kernel", "subprocess_output", "expected"),
    (
        ("6.1.7-200.fc37.x86_64", ("test", 0), True),
        ("6.1.7-200.fc37.x86_64", ("error", 1), False),
    ),
)
def testis_initramfs_file_valid(latest_installed_kernel, subprocess_output, expected, tmpdir, caplog, monkeypatch):
    initramfs_file = tmpdir.mkdir("/boot").join("initramfs-%s.img")
    initramfs_file = str(initramfs_file)
    initramfs_file = initramfs_file % latest_installed_kernel
    with open(initramfs_file, mode="w") as _:
        pass

    monkeypatch.setattr(checks, "INITRAMFS_FILEPATH", initramfs_file)
    monkeypatch.setattr(checks, "run_subprocess", RunSubprocessMocked(return_value=subprocess_output))
    result = checks.is_initramfs_file_valid(initramfs_file)
    assert result == expected

    if not expected:
        assert "Couldn't verify initramfs file. It may be corrupted." in caplog.records[-2].message
        assert "Output of lsinitrd: %s" % subprocess_output[0] in caplog.records[-1].message
