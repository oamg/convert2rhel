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

from collections import namedtuple

import pytest
import six

from convert2rhel import grub, utils
from convert2rhel.unit_tests import run_subprocess_side_effect
from convert2rhel.unit_tests.checks_test import EFIBootInfoMocked


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


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

    monkeypatch.setattr("convert2rhel.grub.is_efi", lambda: is_efi)
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mocked_subproc)
    res = grub.is_secure_boot()
    assert res == expected_res


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
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mock.Mock(return_value=subproc))

    if exception:
        with pytest.raises(exception):
            grub._get_partition(directory)
        assert "grub2-probe returned %s. Output:\n%s" % (subproc[1], subproc[0]) in caplog.records[-1].message
    else:
        assert grub._get_partition(directory) == expected_res
        assert len(caplog.records) == 0
    utils.run_subprocess.assert_called_once_with(
        ["/usr/sbin/grub2-probe", "--target=device", directory], print_output=False
    )


@pytest.mark.parametrize(
    ("expected_res", "device", "exception", "subproc_called", "subproc"),
    (
        ("/dev/sda", "/dev/sda", False, True, (LSBLK_NAME_OUTPUT, 0)),
        (None, "/dev/sda", grub.BootloaderError, True, (LSBLK_NAME_OUTPUT, 1)),
    ),
)
def test__get_blk_device(monkeypatch, caplog, expected_res, device, exception, subproc_called, subproc):
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mock.Mock(return_value=subproc))

    if exception:
        # Device not passed to the _get_blk_device function, or
        # The lsblk call returns non-0 exit code
        with pytest.raises(exception):
            grub._get_blk_device(device)
    else:
        assert grub._get_blk_device(device) == expected_res

    if subproc_called:
        utils.run_subprocess.assert_called_once_with(["lsblk", "-spnlo", "name", device], print_output=False)

    else:
        utils.run_subprocess.assert_not_called()
        assert len(caplog.records) == 0


@pytest.mark.parametrize(
    ("expected_res", "device", "exc", "subproc_called", "subproc"),
    (
        ({"major": 123, "minor": 1}, "/dev/sda", False, True, (LSBLK_NUMBER_OUTPUT, 0)),
        (None, "/dev/sda", grub.BootloaderError, True, (LSBLK_NUMBER_OUTPUT, 1)),
    ),
)
def test__get_device_number(monkeypatch, caplog, expected_res, device, exc, subproc_called, subproc):
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mock.Mock(return_value=subproc))

    if exc:
        # The lsblk call returns non-0 exit code
        with pytest.raises(exc):
            grub._get_device_number(device)
    else:
        assert grub._get_device_number(device) == expected_res

    if subproc_called:
        utils.run_subprocess.assert_called_once_with(["lsblk", "-spnlo", "MAJ:MIN", device], print_output=False)
    else:
        utils.run_subprocess.assert_not_called()
        assert len(caplog.records) == 0


def test_get_boot_partition(monkeypatch):
    monkeypatch.setattr("convert2rhel.grub._get_partition", mock.Mock(return_value="foobar"))
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
    monkeypatch.setattr("convert2rhel.grub.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr("convert2rhel.grub.get_efi_partition", mock.Mock(return_value=partition_res))
    monkeypatch.setattr("convert2rhel.grub.get_boot_partition", mock.Mock(return_value=partition_res))
    monkeypatch.setattr("convert2rhel.grub._get_blk_device", mock.Mock(return_value=expected_res))

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
    monkeypatch.setattr("convert2rhel.grub.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr("os.path.exists", mock.Mock(return_value=path_exists))
    monkeypatch.setattr("os.path.ismount", mock.Mock(return_value=path_ismount))
    monkeypatch.setattr("convert2rhel.grub._get_partition", mock.Mock(return_value=expected_res))

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
    monkeypatch.setattr("convert2rhel.systeminfo.system_info.id", sys_id)

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
def test__remove_efi_centos(sys_id, remove_dir, empty_dir, monkeypatch, caplog):
    monkeypatch.setattr("os.rmdir", mock.Mock())
    monkeypatch.setattr("convert2rhel.systeminfo.system_info.id", sys_id)
    if not empty_dir:
        os.rmdir.side_effect = OSError()

    grub._remove_efi_centos()

    if remove_dir:
        os.rmdir.assert_called_once()
    else:
        os.rmdir.assert_not_called()

    if not empty_dir:
        assert "left untouched" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("is_efi", "efi_file_exists", "copy_files_ok", "replace_entry_exc", "raise_exc", "log_msg"),
    (
        (False, None, None, None, False, "BIOS detected"),
        (True, False, None, None, True, "None of the expected"),
        (True, True, False, None, True, "not been copied"),
        (True, True, True, None, False, "UEFI binary found"),
        (True, True, True, grub.EFINotUsed("No ESP."), True, "No ESP.\nThe migration"),
        (True, True, True, grub.UnsupportedEFIConfiguration("Not mounted."), True, "Not mounted.\nThe migration"),
        (True, True, True, grub.BootloaderError("No device."), True, "No device.\nThe migration"),
    ),
)
def test_post_ponr_set_efi_configuration(
    is_efi, efi_file_exists, copy_files_ok, replace_entry_exc, raise_exc, log_msg, caplog, monkeypatch
):
    monkeypatch.setattr("os.path.exists", mock.Mock(return_value=efi_file_exists))
    monkeypatch.setattr("convert2rhel.grub.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr("convert2rhel.grub._copy_grub_files", mock.Mock(return_value=copy_files_ok))
    monkeypatch.setattr("convert2rhel.grub._remove_efi_centos", mock.Mock())
    monkeypatch.setattr("convert2rhel.grub._replace_efi_boot_entry", mock.Mock())
    if replace_entry_exc:
        grub._replace_efi_boot_entry.side_effect = replace_entry_exc

    if raise_exc:
        with pytest.raises(SystemExit):
            grub.post_ponr_set_efi_configuration()
    else:
        grub.post_ponr_set_efi_configuration()

    assert log_msg in caplog.records[-1].message

    if is_efi and efi_file_exists and copy_files_ok and not replace_entry_exc:
        grub._remove_efi_centos.assert_called_once()
        grub._replace_efi_boot_entry.assert_called_once()


EFIBOOTMGR_VERBOSE_OUTPUT = r"""
BootCurrent: 0004
Timeout: 0 seconds
BootOrder: 0004,0002,0000,0003
Boot0000* UiApp	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)
Boot0002* UEFI Misc Device	PciRoot(0x0)/Pci(0x2,0x3)/Pci(0x0,0x0)N.....YM....R,Y.
Boot0003* EFI Internal Shell	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(7c04a583-9e3e-4f1c-ad65-e05268d0b4d1)
Boot0004* CentOS Linux	HD(1,GPT,714e014a-5636-47b0-a8a7-b5109bfe895c,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)
"""
EFIBOOTMGR_VERBOSE_HEX_ONLY_BOOT_ORDER_OUTPUT = r"""
BootCurrent: 000A
Timeout: 0 seconds
BootOrder: 000A
Boot000A* CentOS Linux	HD(1,GPT,714e014a-5636-47b0-a8a7-b5109bfe895c,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)
"""
EFIBOOTMGR_VERBOSE_MISSING_BOOT_ORDER_OUTPUT = r"""
BootCurrent: 0004
Timeout: 0 seconds
Boot0000* UiApp	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(462caa21-7614-4503-836e-8ab6f4662331)
Boot0002* UEFI Misc Device	PciRoot(0x0)/Pci(0x2,0x3)/Pci(0x0,0x0)N.....YM....R,Y.
Boot0003* EFI Internal Shell	FvVol(7cb8bdc9-f8eb-4f34-aaea-3ee4af6516a1)/FvFile(7c04a583-9e3e-4f1c-ad65-e05268d0b4d1)
Boot0004* CentOS Linux	HD(1,GPT,714e014a-5636-47b0-a8a7-b5109bfe895c,0x800,0x12c000)/File(\EFI\centos\shimx64.efi)
"""
EFIBOOTMGR_VERBOSE_MISSING_CURRENT_BOOT_OUTPUT = r"""
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
    ("is_efi", "subproc_called", "subproc", "total_entries", "current_bootnum", "boot_order", "exception"),
    (
        (False, False, (EFIBOOTMGR_VERBOSE_OUTPUT, 0), 4, "0004", ("0004", "0002", "0000", "0003"), grub.EFINotUsed),
        (True, True, (EFIBOOTMGR_VERBOSE_OUTPUT, 1), 4, "0004", ("0004", "0002", "0000", "0003"), grub.BootloaderError),
        (True, True, (EFIBOOTMGR_VERBOSE_OUTPUT, 0), 4, "0004", ("0004", "0002", "0000", "0003"), False),
        (True, True, (EFIBOOTMGR_VERBOSE_HEX_ONLY_BOOT_ORDER_OUTPUT, 0), 1, "000A", ("000A",), False),
        (True, True, (EFIBOOTMGR_VERBOSE_MISSING_BOOT_ORDER_OUTPUT, 0), 4, "0004", (), grub.BootloaderError),
        (
            True,
            True,
            (EFIBOOTMGR_VERBOSE_MISSING_CURRENT_BOOT_OUTPUT, 0),
            4,
            None,
            ("0004", "0002", "0000", "0003"),
            grub.BootloaderError,
        ),
        (
            True,
            True,
            (EFIBOOTMGR_VERBOSE_MISSING_ENTRIES_OUTPUT, 0),
            None,
            "0004",
            ("0004", "0002", "0000", "0003"),
            grub.BootloaderError,
        ),
    ),
)
def test_efibootinfo(
    monkeypatch, is_efi, subproc_called, subproc, total_entries, current_bootnum, boot_order, exception
):
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mock.Mock(return_value=subproc))
    monkeypatch.setattr("convert2rhel.grub.is_efi", mock.Mock(return_value=is_efi))

    if exception:
        with pytest.raises(exception):
            grub.EFIBootInfo()
    else:
        efibootinfo_obj = grub.EFIBootInfo()
        assert len(efibootinfo_obj.entries) == total_entries
        assert efibootinfo_obj.current_bootnum == current_bootnum
        assert efibootinfo_obj.boot_order == boot_order
        assert current_bootnum in efibootinfo_obj.entries

    if subproc_called:
        utils.run_subprocess.assert_called_once_with(["/usr/sbin/efibootmgr", "-v"], print_output=False)
    else:
        utils.run_subprocess.assert_not_called()


@pytest.mark.parametrize(
    ("efi_bin_path", "label", "expected_ret_val"),
    (
        (r"\EFI\centos\shimx64.efi", "Centos Linux", True),
        (r"\EFI\redhat\shimx64.efi", "Centos Linux", False),
    ),
)
def test__is_rhel_in_boot_entries(efi_bin_path, label, expected_ret_val):
    efibootinfo = EFIBootInfoMocked()

    ret_val = grub._is_rhel_in_boot_entries(efibootinfo, efi_bin_path, label)

    assert ret_val == expected_ret_val


@pytest.mark.parametrize(
    ("efi_file_exists", "exc", "exc_msg", "rhel_entry_exists", "subproc", "log_msg"),
    (
        (True, None, None, True, ("out", 0), "UEFI bootloader entry is already"),
        (True, grub.BootloaderError, "Unable to add a new", False, ("out", 1), None),
        (True, grub.BootloaderError, "Unable to find the new", False, ("out", 0), None),
        (False, grub.BootloaderError, "Unable to detect any", False, ("out", 0), None),
    ),
)
def test__add_rhel_boot_entry(efi_file_exists, exc, exc_msg, rhel_entry_exists, subproc, log_msg, monkeypatch, caplog):
    monkeypatch.setattr("convert2rhel.grub._get_device_number", mock.Mock(return_value={"major": 252, "minor": 1}))
    monkeypatch.setattr("convert2rhel.systeminfo.system_info.version", namedtuple("Version", ["major", "minor"])(8, 5))
    monkeypatch.setattr("convert2rhel.grub.get_efi_partition", mock.Mock(return_value="/dev/sda"))
    monkeypatch.setattr("convert2rhel.grub.get_grub_device", mock.Mock(return_value="/dev/sda"))
    monkeypatch.setattr("os.path.exists", mock.Mock(return_value=efi_file_exists))
    monkeypatch.setattr("convert2rhel.grub._is_rhel_in_boot_entries", mock.Mock(return_value=rhel_entry_exists))
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mock.Mock(return_value=subproc))
    monkeypatch.setattr("convert2rhel.grub.EFIBootInfo", EFIBootInfoMocked())

    if exc:
        with pytest.raises(exc) as exc_info:
            grub._add_rhel_boot_entry("test_arg")
        assert exc_msg in str(exc_info.value)
    else:
        grub._add_rhel_boot_entry("test_arg")
        assert log_msg in caplog.records[-1].message
    if efi_file_exists and not rhel_entry_exists:
        utils.run_subprocess.assert_called_once()


@pytest.mark.parametrize(
    ("orig_removed", "curr_boot_label", "pxe_orig_efi_bin", "efi_bin_exists", "subproc", "log_msg"),
    (
        (True, None, False, False, ("out", 0), "removed already"),
        (False, "Foo Linux", False, False, ("out", 0), "has been modified"),
        (False, None, True, False, ("out", 0), "Unable to get path"),
        (False, None, False, True, ("out", 0), "binary file still exists"),
        (False, None, False, False, ("out", 1), "has failed"),
        (False, None, False, False, ("out", 0), "has been successful"),
    ),
)
def test__remove_orig_boot_entry(
    orig_removed, curr_boot_label, pxe_orig_efi_bin, efi_bin_exists, subproc, log_msg, caplog, monkeypatch
):
    monkeypatch.setattr("os.path.exists", mock.Mock(return_value=efi_bin_exists))
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", mock.Mock(return_value=subproc))
    bootinfo_orig = EFIBootInfoMocked()
    bootinfo_new = EFIBootInfoMocked()

    # Create a new boot entry as a copy of the original boot entry. We need a deep copy (not just a pointer), otherwise
    # the changes to the new entry would be reflected in the orig one as well.
    bootinfo_new.entries["0003"] = copy.deepcopy(bootinfo_orig.entries["0001"])
    bootinfo_new.entries["0003"].boot_number = "0003"
    bootinfo_new.boot_order = ("0003", "0002")

    if orig_removed:
        del bootinfo_new.entries["0001"]

    if curr_boot_label:
        # change label of the original current boot entry
        bootinfo_orig.entries["0001"].label = curr_boot_label

    if pxe_orig_efi_bin:
        monkeypatch.setattr("convert2rhel.grub.EFIBootLoader.get_canonical_path", mock.Mock(return_value=None))

    if efi_bin_exists:
        # make sure the new entry efi bin path is different from the original entry one
        bootinfo_new.entries["0003"].efi_bin_source = r"File(\random\bin\path.efi)"

    grub._remove_orig_boot_entry(bootinfo_orig, bootinfo_new)

    assert log_msg in caplog.records[-1].message
    if not orig_removed and not curr_boot_label and not pxe_orig_efi_bin and not efi_bin_exists:
        utils.run_subprocess.assert_called_once()


@pytest.mark.parametrize(
    ("releasever_major", "is_efi", "config_path", "grub2_mkconfig_exit_code", "grub2_install_exit_code", "expected"),
    (
        (8, True, "/boot/efi/EFI/redhat/grub.cfg", 0, 0, "Successfully updated GRUB2 on the system."),
        (8, False, "/boot/grub2/grub.cfg", 0, 0, "Successfully updated GRUB2 on the system."),
        (7, False, "/boot/grub2/grub.cfg", 0, 1, "Couldn't install the new images with GRUB2."),
        (7, False, "/boot/grub2/grub.cfg", 1, 1, "GRUB2 config file generation failed."),
        (
            6,
            False,
            "/boot/grub/grub.conf",
            1,
            1,
            "Convert2RHEL does not install updated GRUB Legacy bootloader image on RHEL 6.",
        ),
    ),
)
def test_update_grub_after_conversion(
    releasever_major,
    is_efi,
    config_path,
    grub2_mkconfig_exit_code,
    grub2_install_exit_code,
    expected,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr("convert2rhel.grub.get_grub_device", mock.Mock(return_value="/dev/sda"))
    monkeypatch.setattr("convert2rhel.grub.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr(
        "convert2rhel.systeminfo.system_info.version", namedtuple("Version", ["major"])(releasever_major)
    )
    run_subprocess_mocked = mock.Mock(
        spec=utils.run_subprocess,
        side_effect=run_subprocess_side_effect(
            (
                (
                    "/usr/sbin/grub2-mkconfig",
                    "-o",
                    "%s" % config_path,
                ),
                (
                    "output",
                    grub2_mkconfig_exit_code,
                ),
            ),
            (("/usr/sbin/grub2-install", "/dev/sda"), ("output", grub2_install_exit_code)),
        ),
    )
    monkeypatch.setattr(
        utils,
        "run_subprocess",
        value=run_subprocess_mocked,
    )

    grub.update_grub_after_conversion()
    if expected is not None:
        assert expected in caplog.records[-1].message
