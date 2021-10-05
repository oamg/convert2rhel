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

import copy
import os
import sys

import pytest

from convert2rhel import grub, utils
from convert2rhel.systeminfo import system_info


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
        assert "grub2-probe returned %s. Output:\n%s" % (subproc[1], subproc[0]) in caplog.records[-1].message
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
        # Device not passed to the _get_blk_device function, or
        # The lsblk call returns non-0 exit code
        with pytest.raises(exception):
            grub._get_blk_device(device)
    else:
        assert grub._get_blk_device(device) == expected_res

    if subproc_called:
        utils.run_subprocess.assert_called_once_with("lsblk -spnlo name %s" % device, print_output=False)

    else:
        utils.run_subprocess.assert_not_called()
        assert len(caplog.records) == 0


@pytest.mark.parametrize(
    ("expected_res", "device", "exc", "subproc_called", "subproc"),
    (
        ({"major": 123, "minor": 1}, "/dev/sda", False, True, (LSBLK_NUMBER_OUTPUT, 0)),
        (None, "/dev/sda", grub.BootloaderError, True, (LSBLK_NUMBER_OUTPUT, 1)),
        (None, None, ValueError, False, (None, 0)),
    ),
)
def test__get_device_number(monkeypatch, caplog, expected_res, device, exc, subproc_called, subproc):
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=subproc))

    if exc:
        # Device not passed to the _get_device_number function, or
        # The lsblk call returns non-0 exit code
        with pytest.raises(exc):
            grub._get_device_number(device)
    else:
        assert grub._get_device_number(device) == expected_res

    if subproc_called:
        utils.run_subprocess.assert_called_once_with("lsblk -spnlo MAJ:MIN %s" % device, print_output=False)
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
        (None, grub.EFINotUsed, True, True, False),
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


def get_local_efibootloader():
    """Get an EFIBootLoader instance for a boot entry pointing to a local file."""
    return grub.EFIBootLoader(
        boot_number="0002",
        label="Red Hat Enterprise Linux",
        active=True,
        efi_bin_source=r"HD(1,GPT,012583b3-e5c5-4fb5-b779-a6fc6b9fc85b,0x800,0x64000)/File(\EFI\redhat\shimx64.efi)",
    )


def get_pxe_efibootloader():
    """Get an EFIBootLoader instance for a boot entry pointing to a network (PXE)."""
    return grub.EFIBootLoader(
        boot_number="Boot000D",
        label="Red Hat Enterprise Linux",
        active=True,
        efi_bin_source=r"VenMsg(bc7838d2-0f82-4d60-8316-c068ee79d25b,78a84aaf2b2afc4ea79cf5cc8f3d3803)",
    )


def test_EFIBootLoader_eq_neq():
    efibootloader_a = get_local_efibootloader()
    efibootloader_a_copy = copy.deepcopy(efibootloader_a)

    efibootloader_b = get_pxe_efibootloader()

    assert efibootloader_a == efibootloader_a_copy
    assert efibootloader_b != efibootloader_a


def test_EFIBootLoader_is_referring_to_file():
    efibootloader_local = get_local_efibootloader()
    assert efibootloader_local.is_referring_to_file()

    efibootloader_pxe = get_pxe_efibootloader()
    assert not efibootloader_pxe.is_referring_to_file()


@pytest.mark.parametrize(
    ("efibootloader", "return_value"),
    ((get_local_efibootloader(), "/boot/efi/EFI/redhat/shimx64.efi"), (get_pxe_efibootloader(), None)),
)
def test_EFIBootLoader_get_canonical_path(efibootloader, return_value):
    assert efibootloader.get_canonical_path() == return_value


def test_EFIBootLoader__efi_path_to_canonical():
    efi_bin_source = r"\EFI\redhat\shimx64.efi"
    assert grub.EFIBootLoader._efi_path_to_canonical(efi_bin_source) == "/boot/efi/EFI/redhat/shimx64.efi"


@pytest.mark.parametrize(
    ("sys_id", "src_file_exists", "dst_file_exists", "log_msg", "ret_value"),
    (
        ("oracle", None, None, "only related to CentOS Linux", True),
        ("centos", None, True, "file already exists", True),
        ("centos", True, False, "Copying '", True),
        ("centos", False, False, "Unable to find the original", False),
    ),
)
@mock.patch("shutil.copy2")
@mock.patch("os.path.exists")
def test__copy_grub_files(
    mock_path_exists, mock_path_copy2, sys_id, src_file_exists, dst_file_exists, log_msg, ret_value, monkeypatch, caplog
):
    def path_exists(path):
        return src_file_exists if grub.CENTOS_EFIDIR_CANONICAL_PATH in path else dst_file_exists

    mock_path_exists.side_effect = path_exists
    monkeypatch.setattr(system_info, "id", sys_id)

    successful = grub._copy_grub_files(["grubenv", "grub.cfg"], ["user.cfg"])

    assert any(log_msg in record.message for record in caplog.records)
    assert successful == ret_value
    if sys_id == "centos" and src_file_exists and not dst_file_exists:
        assert mock_path_copy2.call_args_list == [
            mock.call("/boot/efi/EFI/centos/grubenv", "/boot/efi/EFI/redhat/grubenv"),
            mock.call("/boot/efi/EFI/centos/grub.cfg", "/boot/efi/EFI/redhat/grub.cfg"),
            mock.call("/boot/efi/EFI/centos/user.cfg", "/boot/efi/EFI/redhat/user.cfg"),
        ]


@pytest.mark.parametrize(
    ("sys_id", "remove_dir", "empty_dir"),
    (
        ("oracle", False, True),
        ("centos", True, True),
        ("centos", True, False),
    ),
)
@mock.patch("os.rmdir")
def test__remove_efi_centos(mock_rmdir, sys_id, remove_dir, empty_dir, monkeypatch, caplog):
    monkeypatch.setattr(system_info, "id", sys_id)
    if not empty_dir:
        mock_rmdir.side_effect = OSError()

    grub._remove_efi_centos()

    if remove_dir:
        mock_rmdir.assert_called_once()
    else:
        mock_rmdir.assert_not_called()

    if not empty_dir:
        assert "left untouched" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("is_efi", "efi_file_exists", "copy_files_ok", "replace_entry_ok", "raise_exc", "log_msg"),
    (
        (False, None, None, None, False, "BIOS detected"),
        (True, False, None, None, True, "None of the expected"),
        (True, True, False, None, True, "not been copied"),
        (True, True, True, True, False, "UEFI binary found"),
        (True, True, True, False, True, "not successful"),
    ),
)
@mock.patch("convert2rhel.grub.is_efi")
@mock.patch("convert2rhel.grub._copy_grub_files")
@mock.patch("convert2rhel.grub._remove_efi_centos")
@mock.patch("convert2rhel.grub._replace_efi_boot_entry")
@mock.patch("os.path.exists")
def test_post_ponr_set_efi_configuration(
    mock_path_exists,
    mock_replace_boot_entry,
    mock_remove_folder,
    mock_copy_files,
    mock_is_efi,
    is_efi,
    efi_file_exists,
    copy_files_ok,
    replace_entry_ok,
    raise_exc,
    log_msg,
    caplog,
):
    mock_is_efi.return_value = is_efi
    mock_path_exists.return_value = efi_file_exists
    mock_copy_files.return_value = copy_files_ok
    if not replace_entry_ok:
        mock_replace_boot_entry.side_effect = grub.BootloaderError("err")

    if raise_exc:
        with pytest.raises(SystemExit):
            grub.post_ponr_set_efi_configuration()
    else:
        grub.post_ponr_set_efi_configuration()

    assert log_msg in caplog.records[-1].message

    if is_efi and efi_file_exists and copy_files_ok and replace_entry_ok:
        mock_remove_folder.assert_called_once()
        mock_replace_boot_entry.assert_called_once()


EFIBOOTMGR_VERBOSE_OUTPUT = """
BootCurrent: 0004
Timeout: 0 seconds
BootOrder: 0004,0002,0000,0003
Boot0000* UiApp	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)
Boot0002* UEFI Misc Device	PciRoot(0x0)/Pci(0x2,0x3)/Pci(0x0,0x0)N.....YM....R,Y.
Boot0003* EFI Internal Shell	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(7c04a583-9e3e-4f1c-ad65-e05268d0b4d1)
Boot0004* CentOS Linux	HD(1,GPT,714e014a-5636-47b0-a8a7-b5109bfe895c,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)
"""
EFIBOOTMGR_VERBOSE_MISSING_BOOT_ORDER_OUTPUT = """
BootCurrent: 0004
Timeout: 0 seconds
Boot0000* UiApp	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)
Boot0002* UEFI Misc Device	PciRoot(0x0)/Pci(0x2,0x3)/Pci(0x0,0x0)N.....YM....R,Y.
Boot0003* EFI Internal Shell	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(7c04a583-9e3e-4f1c-ad65-e05268d0b4d1)
Boot0004* CentOS Linux	HD(1,GPT,714e014a-5636-47b0-a8a7-b5109bfe895c,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)
"""
EFIBOOTMGR_VERBOSE_MISSING_CURRENT_BOOT_OUTPUT = """
Timeout: 0 seconds
BootOrder: 0004,0002,0000,0003
Boot0000* UiApp	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)
Boot0002* UEFI Misc Device	PciRoot(0x0)/Pci(0x2,0x3)/Pci(0x0,0x0)N.....YM....R,Y.
Boot0003* EFI Internal Shell	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(7c04a583-9e3e-4f1c-ad65-e05268d0b4d1)
Boot0004* CentOS Linux	HD(1,GPT,714e014a-5636-47b0-a8a7-b5109bfe895c,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)
"""
EFIBOOTMGR_VERBOSE_MISSING_ENTRIES_OUTPUT = """
BootCurrent: 0004
Timeout: 0 seconds
BootOrder: 0004,0002,0000,0003
"""


@pytest.mark.parametrize(
    ("is_efi", "subproc_called", "subproc", "exception"),
    (
        (False, False, (EFIBOOTMGR_VERBOSE_OUTPUT, 0), grub.EFINotUsed),
        (True, True, (EFIBOOTMGR_VERBOSE_OUTPUT, 1), grub.BootloaderError),
        (True, True, (EFIBOOTMGR_VERBOSE_OUTPUT, 0), False),
        (True, True, (EFIBOOTMGR_VERBOSE_MISSING_BOOT_ORDER_OUTPUT, 0), grub.BootloaderError),
        (True, True, (EFIBOOTMGR_VERBOSE_MISSING_CURRENT_BOOT_OUTPUT, 0), grub.BootloaderError),
        (True, True, (EFIBOOTMGR_VERBOSE_MISSING_ENTRIES_OUTPUT, 0), grub.BootloaderError),
    ),
)
def test_efibootinfo(monkeypatch, is_efi, subproc_called, subproc, exception):
    monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=subproc))
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=is_efi))

    efibootinfo_obj = None
    if exception:
        with pytest.raises(exception):
            grub.EFIBootInfo()
    else:
        efibootinfo_obj = grub.EFIBootInfo()
        assert len(efibootinfo_obj.entries) == 4
        assert efibootinfo_obj.current_bootnum == "0004"
        assert efibootinfo_obj.boot_order == ("0004", "0002", "0000", "0003")

    if subproc_called:
        utils.run_subprocess.assert_called_once_with("/usr/sbin/efibootmgr -v", print_output=False)
    else:
        utils.run_subprocess.assert_not_called()


# TODO(egustavs): _is_rhel_in_boot_entries
# TODO(pstodulk): _add_rhel_boot_entry
# TODO(pstodulk): _remove_orig_boot_entry
