# -*- coding: utf-8 -*-
#
# Copyright(C) 2024 Red Hat, Inc.
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

import copy
import os

from collections import namedtuple

import pytest
import six

from convert2rhel import utils
from convert2rhel.bootloader import bootloader, grub
from convert2rhel.unit_tests import RunSubprocessMocked, run_subprocess_side_effect


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


# TODO(pstodulk): put here a real examples of an output..
_SEC_STDOUT_ENABLED = "secure boot enabled"
_SEC_STDOUT_DISABLED = "e.g. nothing..."

LSBLK_NAME_OUTPUT = """/dev/sda
/dev/sda
"""
BLKID_NUMBER_OUTPUT = '/dev/sda1: PART_ENTRY_NUMBER="1"'


@pytest.mark.parametrize(
    ("expected_res", "directory", "exception", "subproc"),
    (
        ("foo", "/boot", False, (" foo ", 0)),
        (None, "/bar", grub.BootloaderError, (None, 0)),
        (None, "/baz", grub.BootloaderError, (" foo ", 1)),
        (None, "/bez", grub.BootloaderError, (None, 1)),
    ),
)
def test_get_partition(monkeypatch, caplog, expected_res, directory, exception, subproc):
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", RunSubprocessMocked(return_value=subproc))

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
    monkeypatch.setattr("convert2rhel.utils.run_subprocess", RunSubprocessMocked(return_value=subproc))

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
    ("expected_res", "partition_res", "is_efi"),
    (
        ("/dev/sda", "get_efi_partition", True),
        ("/dev/sda", "get_boot_partition", False),
    ),
)
def test_get_grub_device(monkeypatch, expected_res, partition_res, is_efi):
    monkeypatch.setattr("convert2rhel.bootloader.bootloader.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr("convert2rhel.bootloader.grub.get_efi_partition", mock.Mock(return_value=partition_res))
    monkeypatch.setattr("convert2rhel.bootloader.grub.get_boot_partition", mock.Mock(return_value=partition_res))
    monkeypatch.setattr("convert2rhel.bootloader.grub._get_blk_device", mock.Mock(return_value=expected_res))

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
    monkeypatch.setattr("convert2rhel.bootloader.bootloader.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr("os.path.exists", mock.Mock(return_value=path_exists))
    monkeypatch.setattr("os.path.ismount", mock.Mock(return_value=path_ismount))
    monkeypatch.setattr("convert2rhel.bootloader.grub._get_partition", mock.Mock(return_value=expected_res))

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


def test_get_boot_partition(monkeypatch):
    monkeypatch.setattr("convert2rhel.bootloader.grub._get_partition", mock.Mock(return_value="foobar"))
    assert grub.get_boot_partition() == "foobar"
    grub._get_partition.assert_called_once_with("/boot")


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
    ("is_efi", "config_path"),
    (
        (False, "/boot/grub2/grub.cfg"),
        (True, "/boot/efi/EFI/redhat/grub.cfg"),
    ),
)
def test_get_grub_config_file(is_efi, config_path, monkeypatch):
    monkeypatch.setattr("convert2rhel.bootloader.bootloader.is_efi", mock.Mock(return_value=is_efi))
    config_file = grub.get_grub_config_file()

    assert config_file == config_path


@pytest.mark.parametrize(
    ("releasever_major", "is_efi", "config_path", "grub2_mkconfig_exit_code", "grub2_install_exit_code", "expected"),
    (
        (8, True, "/boot/efi/EFI/redhat/grub.cfg", 0, 0, "Successfully updated GRUB2 on the system."),
        (8, False, "/boot/grub2/grub.cfg", 0, 0, "Successfully updated GRUB2 on the system."),
        (7, False, "/boot/grub2/grub.cfg", 0, 1, "Couldn't install the new images with GRUB2."),
        (7, False, "/boot/grub2/grub.cfg", 1, 1, "GRUB2 config file generation failed."),
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
    monkeypatch.setattr("convert2rhel.bootloader.grub.get_grub_device", mock.Mock(return_value="/dev/sda"))
    monkeypatch.setattr("convert2rhel.bootloader.bootloader.is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr(
        "convert2rhel.systeminfo.system_info.version", namedtuple("Version", ["major"])(releasever_major)
    )
    run_subprocess_mocked = RunSubprocessMocked(
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
