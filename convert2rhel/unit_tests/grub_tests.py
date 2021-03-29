# -*- coding: utf-8 -*-
#
# Copyright(C) 2021 Red Hat, Inc.
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

from collections import namedtuple
import os
import subprocess
import sys

import pytest

from convert2rhel import grub, unit_tests, utils
from convert2rhel.unit_tests import GetLoggerMocked


try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


# TODO(pstodulk): put here a real examples of an output..
_SEC_STDOUT_ENABLED = "secure boot enabled"
_SEC_STDOUT_DISABLED = "e.g. nothing..."
# subproc is tuple (stdout, ecode) or None in case exception should be raised
@pytest.mark.parametrize(("expected_res", "is_efi", "subproc"), (
    (False, False, (_SEC_STDOUT_ENABLED, 0)),
    (False, False, (_SEC_STDOUT_DISABLED, 0)),
    (False, False, ("", 1)),
    (False, True, ("", 1)),
    (False, True, (_SEC_STDOUT_ENABLED, 1)), # seems to be invalid case, but..
    (False, True, (_SEC_STDOUT_DISABLED, 0)),
    (False, True, None),
    (True, True, (_SEC_STDOUT_ENABLED, 0)),
))
def test_is_secure_boot(monkeypatch, expected_res, is_efi, subproc):
    def mocked_subproc(dummyCMD, print_output=False):
        if subproc is None:
            raise OSError("dummy error msg")
        return subproc

    monkeypatch.setattr(grub, "is_efi", lambda: is_efi)
    monkeypatch.setattr(utils, "run_subprocess", mocked_subproc)
    res = grub.is_secure_boot()
    assert res == expected_res


@pytest.mark.parametrize("canonical_path", (
    "",
    "/boot/efii/EFI/something.efi",
    "/boot/grub/something.efi",
    "EFI/path/grubx.efi",
    "/boot/EFI/EFI/something.efi",
    "/boot/efi",
))
def test_canonical_path_to_efi_format_err(canonical_path):
    with pytest.raises(ValueError):
        grub.canonical_path_to_efi_format(canonical_path)


@pytest.mark.parametrize(("canonical_path", "efi_path"), (
    ("/boot/efi/EFI/centos/shimx64.efi", "\\EFI\\centos\\shimx64.efi"),
    ("/boot/efi/EFI/redhat/shimx64.efi", "\\EFI\\redhat\\shimx64.efi"),
    ("/boot/efi/EFI/shimx64.efi", "\\EFI\\shimx64.efi"),
    ("/boot/efi/EFI/another/path/something.efi", "\\EFI\\another\\path\\something.efi"),
    ("/boot/efi/EFI/centos/efibin", "\\EFI\\centos\\efibin"),
))
def test_canonical_path_to_efi_format(canonical_path, efi_path):
    assert grub.canonical_path_to_efi_format(canonical_path) == efi_path


# TODO(pstodulk): _get_partition
# TODO(pstodulk): _get_blk_device
# TODO(pstodulk): _get_device_number
# TODO(pstodulk): get_boot_partition
# TODO(pstodulk): get_grub_device
# TODO(pstodulk): get_efi_partition
# TODO(pstodulk): EFIBootLoader
# TODO(pstodulk): EFIBootInfo
# TODO(pstodulk): _copy_grub_files
# TODO(pstodulk): _create_new_entry
# TODO(pstodulk): _remove_current_boot_entry
# TODO(pstodulk): _remove_efi_centos
# TODO(pstodulk): post_ponr_set_efi_configuration
