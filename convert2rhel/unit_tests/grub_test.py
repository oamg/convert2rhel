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

import os
import subprocess
import sys

from collections import namedtuple

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

LSBLK_NAME_OUTPUT = """/dev/sda
/dev/sda
"""
LSBLK_NUMBER_OUTPUT = """123:1
259:0
"""
# subproc is tuple (stdout, ecode) or None in case exception should be raised
@pytest.mark.parametrize(
    ("expected_res", "is_efi", "subproc"),
    (
        (False, False, (_SEC_STDOUT_ENABLED, 0)),
        (False, False, (_SEC_STDOUT_DISABLED, 0)),
        (False, False, ("", 1)),
        (False, True, ("", 1)),
        (False, True, (_SEC_STDOUT_ENABLED, 1)),  # seems to be invalid case, but..
        (False, True, (_SEC_STDOUT_DISABLED, 0)),
        (False, True, None),
        (True, True, (_SEC_STDOUT_ENABLED, 0)),
    ),
)
def test_is_secure_boot(monkeypatch, expected_res, is_efi, subproc):
    def mocked_subproc(dummyCMD, print_output=False):
        if subproc is None:
            raise OSError("dummy error msg")
        return subproc

    monkeypatch.setattr(grub, "is_efi", lambda: is_efi)
    monkeypatch.setattr(utils, "run_subprocess", mocked_subproc)
    res = grub.is_secure_boot()
    assert res == expected_res


@pytest.mark.parametrize(
    "canonical_path",
    (
        "",
        "/boot/efii/EFI/something.efi",
        "/boot/grub/something.efi",
        "EFI/path/grubx.efi",
        "/boot/EFI/EFI/something.efi",
        "/boot/efi",
    ),
)
def test_canonical_path_to_efi_format_err(canonical_path):
    with pytest.raises(ValueError):
        grub.canonical_path_to_efi_format(canonical_path)


@pytest.mark.parametrize(
    ("canonical_path", "efi_path"),
    (
        ("/boot/efi/EFI/centos/shimx64.efi", "\\EFI\\centos\\shimx64.efi"),
        ("/boot/efi/EFI/redhat/shimx64.efi", "\\EFI\\redhat\\shimx64.efi"),
        ("/boot/efi/EFI/shimx64.efi", "\\EFI\\shimx64.efi"),
        ("/boot/efi/EFI/another/path/something.efi", "\\EFI\\another\\path\\something.efi"),
        ("/boot/efi/EFI/centos/efibin", "\\EFI\\centos\\efibin"),
    ),
)
def test_canonical_path_to_efi_format(canonical_path, efi_path):
    assert grub.canonical_path_to_efi_format(canonical_path) == efi_path


@pytest.mark.parametrize(
    ("expected_res", "directory", "exception", "subproc"),
    (
        ("foo", "/boot", False, (" foo ", 0)),
        (None, "/bar", grub.BootloaderError, (None, 0)),
        (None, "/baz", grub.BootloaderError, (" foo ", 1)),
        (None, "/bez", grub.BootloaderError, (None, 1)),
    ),
)
def test__get_partition(monkeypatch, caplog, expected_res, directory, exception, subproc):
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=subproc))

    if exception:
        with pytest.raises(exception):
            grub._get_partition(directory)
        assert "grub2-probe ended with non-zero exit code.\n%s" % subproc[0] in caplog.records[-1].message
    else:
        assert grub._get_partition(directory) == expected_res
        assert len(caplog.records) == 0
    utils.run_subprocess.assert_called_once_with(
        "/usr/sbin/grub2-probe --target=device %s" % directory, print_output=False
    )


@pytest.mark.parametrize(
    ("expected_res", "device", "exception", "subproc_called", "subproc"),
    (
        ("/dev/sda", "/dev/sda", False, True, (LSBLK_NAME_OUTPUT, 0)),
        (None, "/dev/sda", grub.BootloaderError, True, (LSBLK_NAME_OUTPUT, 1)),
        (None, None, ValueError, False, (None, 0)),
    ),
)
def test__get_blk_device(monkeypatch, caplog, expected_res, device, exception, subproc_called, subproc):
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=subproc))

    if exception:
        with pytest.raises(exception):
            grub._get_blk_device(device)
    else:
        assert grub._get_blk_device(device) == expected_res

    if subproc_called:
        utils.run_subprocess.assert_called_once_with("lsblk -spnlo name %s" % device, print_output=False)
        if subproc[1]:
            assert "Cannot get the block device for '%s'." % device in caplog.text
        else:
            assert caplog.text == ""
    else:
        utils.run_subprocess.assert_not_called()
        assert len(caplog.records) == 0


@pytest.mark.parametrize(
    ("expected_res", "device", "exception", "subproc_called", "subproc"),
    (
        ({"major": 123, "minor": 1}, "/dev/sda", False, True, (LSBLK_NUMBER_OUTPUT, 0)),
        (None, "/dev/sda", False, True, (LSBLK_NUMBER_OUTPUT, 1)),
        (None, None, ValueError, False, (None, 0)),
    ),
)
def test__get_device_number(monkeypatch, caplog, expected_res, device, exception, subproc_called, subproc):
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=subproc))

    if exception:
        with pytest.raises(exception):
            grub._get_device_number(device)
    else:
        assert grub._get_device_number(device) == expected_res

    if subproc_called:
        utils.run_subprocess.assert_called_once_with("lsblk -spnlo MAJ:MIN %s" % device, print_output=False)
        if subproc[1]:
            assert "Cannot get information about the '%s' device." % device in caplog.text
        else:
            assert caplog.text == ""
    else:
        utils.run_subprocess.assert_not_called()
        assert len(caplog.records) == 0


def test_get_boot_partition(monkeypatch):
    monkeypatch.setattr(grub, "_get_partition", mock.Mock(return_value="foobar"))
    assert grub.get_boot_partition() == "foobar"
    grub._get_partition.assert_called_once_with("/boot")


@pytest.mark.parametrize(
    ("expected_res", "partition_res", "is_efi"),
    (
        ("/dev/sda", "get_efi_partition", True),
        ("/dev/sda", "get_boot_partition", False),
    ),
)
def test_get_grub_device(monkeypatch, expected_res, partition_res, is_efi):
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr(grub, "get_efi_partition", mock.Mock(return_value=partition_res))
    monkeypatch.setattr(grub, "get_boot_partition", mock.Mock(return_value=partition_res))
    monkeypatch.setattr(grub, "_get_blk_device", mock.Mock(return_value=expected_res))

    assert grub.get_grub_device() == expected_res

    if is_efi:
        grub.get_efi_partition.assert_called_once()
        grub.get_boot_partition.assert_not_called()
    else:
        grub.get_efi_partition.assert_not_called()
        grub.get_boot_partition.assert_called_once()
    grub._get_blk_device.assert_called_once_with(partition_res)


@pytest.mark.parametrize(
    ("expected_res", "exception", "path_exists", "path_ismount", "is_efi"),
    (
        ("/dev/sda", False, True, True, True),
        (None, grub.NotUsedEFI, True, True, False),
        (None, grub.UnsupportedEFIConfiguration, True, False, True),
        (None, grub.UnsupportedEFIConfiguration, False, True, True),
        (None, grub.UnsupportedEFIConfiguration, False, False, True),
    ),
)
def test_get_efi_partition(monkeypatch, expected_res, exception, path_exists, path_ismount, is_efi):
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr(os.path, "exists", mock.Mock(return_value=path_exists))
    monkeypatch.setattr(os.path, "ismount", mock.Mock(return_value=path_ismount))
    monkeypatch.setattr(grub, "_get_partition", mock.Mock(return_value=expected_res))

    if exception:
        with pytest.raises(exception):
            grub.get_efi_partition()
        grub._get_partition.assert_not_called()
    else:
        grub.get_efi_partition()
        grub._get_partition.assert_called_once_with(grub.EFI_MOUNTPOINT)

    if is_efi:
        if not path_exists:
            os.path.exists.assert_called_once()
            os.path.ismount.assert_not_called()
        else:
            os.path.exists.assert_called_once()
            os.path.ismount.assert_called_once()


# TODO(pstodulk): get_efi_partition
# TODO(pstodulk): EFIBootLoader
# TODO: is_efi

# TODO(pstodulk): EFIBootInfo
# TODO(pstodulk): _copy_grub_files
# TODO(egustavs): _check_rhel_boot_entry
# TODO(pstodulk): _create_rhel_boot_entry
# TODO(pstodulk): _remove_current_boot_entry
# TODO(pstodulk): _remove_efi_centos
# TODO(pstodulk): post_ponr_set_efi_configuration
