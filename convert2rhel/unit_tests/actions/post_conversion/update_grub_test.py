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

from collections import namedtuple

import pytest
import six

from convert2rhel import actions, grub, unit_tests, utils
from convert2rhel.actions.post_conversion import update_grub
from convert2rhel.unit_tests import RunSubprocessMocked, run_subprocess_side_effect


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def update_grub_instance():
    return update_grub.UpdateGrub()


@pytest.mark.parametrize(
    ("releasever_major", "is_efi", "config_path", "grub2_mkconfig_exit_code", "grub2_install_exit_code", "expected"),
    (
        (8, True, "/boot/efi/EFI/redhat/grub.cfg", 0, 0, "Successfully updated GRUB2 on the system."),
        (8, False, "/boot/grub2/grub.cfg", 0, 0, "Successfully updated GRUB2 on the system."),
        (7, False, "/boot/grub2/grub.cfg", 0, 1, "Couldn't install the new images with GRUB2."),
        (7, False, "/boot/grub2/grub.cfg", 1, 1, "GRUB2 config file generation failed."),
    ),
)
def test_update_grub(
    update_grub_instance,
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
    run_subprocess_mocked = RunSubprocessMocked(
        side_effect=run_subprocess_side_effect(
            (
                (
                    "/usr/sbin/grub2-mkconfig",
                    "-o",
                    "{}".format(config_path),
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

    update_grub_instance.run()
    if expected is not None:
        assert expected in caplog.records[-1].message


@pytest.mark.parametrize(
    ("config_path", "is_efi", "grub2_mkconfig_exit_code", "grub2_install_exit_code", "releasever_major", "expected"),
    (
        (
            "/boot/grub2/grub.cfg",
            True,
            1,
            0,
            9,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="GRUB2_CONFIG_CREATION_FAILED",
                        title="The grub2-mkconfig call failed to complete",
                        description=(
                            "There may be issues with the bootloader configuration."
                            " Follow the recommended remediation before rebooting the system."
                        ),
                        diagnosis="The grub2-mkconfig call failed with output:\n'output'",
                        remediations="Resolve the problem reported in the diagnosis and then run 'grub2-mkconfig -o"
                        " /boot/grub2/grub.cfg' and 'grub2-install [block device, e.g. /dev/sda]'.",
                    ),
                )
            ),
        ),
        (
            "/boot/efi/EFI/redhat/grub.cfg",
            True,
            1,
            0,
            7,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="GRUB2_CONFIG_CREATION_FAILED",
                        title="The grub2-mkconfig call failed to complete",
                        description=(
                            "There may be issues with the bootloader configuration."
                            " Follow the recommended remediation before rebooting the system."
                        ),
                        diagnosis="The grub2-mkconfig call failed with output:\n'output'",
                        remediations="Resolve the problem reported in the diagnosis and then run 'grub2-mkconfig -o"
                        " /boot/efi/EFI/redhat/grub.cfg' and 'grub2-install [block device, e.g. /dev/sda]'.",
                    ),
                )
            ),
        ),
        (
            "/boot/grub2/grub.cfg",
            False,
            1,
            0,
            7,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="GRUB2_CONFIG_CREATION_FAILED",
                        title="The grub2-mkconfig call failed to complete",
                        description=(
                            "There may be issues with the bootloader configuration."
                            " Follow the recommended remediation before rebooting the system."
                        ),
                        diagnosis="The grub2-mkconfig call failed with output:\n'output'",
                        remediations="Resolve the problem reported in the diagnosis and then run 'grub2-mkconfig -o"
                        " /boot/grub2/grub.cfg' and 'grub2-install [block device, e.g. /dev/sda]'.",
                    ),
                )
            ),
        ),
        (
            "/boot/grub2/grub.cfg",
            False,
            0,
            1,
            7,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="GRUB2_INSTALL_FAILED",
                        title="The grub2-install call failed to complete",
                        description="The grub2-install call failed with output: 'output'. The conversion will continue but there may be issues with the current grub2 image formats.",
                        diagnosis=None,
                        remediations="If there are issues with the current grub2 image we recommend manually re-generating it with 'grub2-install [block device, e.g. /dev/sda]'.",
                    ),
                )
            ),
        ),
    ),
)
def test_update_grub_action_messages(
    update_grub_instance,
    monkeypatch,
    config_path,
    is_efi,
    grub2_mkconfig_exit_code,
    grub2_install_exit_code,
    releasever_major,
    expected,
):
    monkeypatch.setattr("convert2rhel.grub.get_grub_device", mock.Mock(return_value="/dev/sda"))
    monkeypatch.setattr("convert2rhel.grub.get_grub_config_file", mock.Mock(return_value=config_path))
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=is_efi))
    monkeypatch.setattr(
        "convert2rhel.systeminfo.system_info.version", namedtuple("Version", ["major"])(releasever_major)
    )
    run_subprocess_mocked = RunSubprocessMocked(
        side_effect=run_subprocess_side_effect(
            (
                (
                    "/usr/sbin/grub2-mkconfig",
                    "-o",
                    "{}".format(config_path),
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

    update_grub_instance.run()
    assert expected.issuperset(update_grub_instance.messages)
    assert expected.issubset(update_grub_instance.messages)


@pytest.mark.parametrize(
    ("get_partition_error", "get_blk_device_error", "diagnosis"),
    (
        (True, False, "Unable to get device information for"),
        (False, True, "Unable to get a block device for"),
    ),
)
def test_update_grub_error(update_grub_instance, monkeypatch, get_partition_error, get_blk_device_error, diagnosis):
    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_code=0))
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=False))
    if get_partition_error:
        monkeypatch.setattr(grub, "_get_partition", mock.Mock(side_effect=grub.BootloaderError(diagnosis)))
    if get_blk_device_error:
        monkeypatch.setattr(grub, "_get_blk_device", mock.Mock(side_effect=grub.BootloaderError(diagnosis)))

    update_grub_instance.run()

    unit_tests.assert_actions_result(
        update_grub_instance,
        level="ERROR",
        id="FAILED_TO_IDENTIFY_GRUB2_BLOCK_DEVICE",
        title="Failed to identify GRUB2 block device",
        description="The block device could not be identified. Look at the diagnosis for more information.",
        diagnosis=diagnosis,
    )
