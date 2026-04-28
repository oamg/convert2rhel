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
        description="The block device could not be identified, please look at the diagnosis " "for more information.",
        diagnosis=diagnosis,
    )


_GRUB_DISTRIBUTOR_OPT = "GRUB_DISTRIBUTOR=\"$(sed 's, release .*$,,g' /etc/system-release)\""
_GRUB_DISABLE_SUBMENU_OPT = 'GRUB_DISABLE_SUBMENU="true"'


@pytest.mark.parametrize(
    ("releasever_major", "file_content", "expected_content", "expected_log", "expect_write"),
    [
        pytest.param(
            3,
            'GRUB_TERMINAL="ec2-console"\n',
            None,
            "Not running Amazon Linux 2, skipping.",
            False,
            id="not_al2_skip",
        ),
        pytest.param(
            2,
            'GRUB_TERMINAL="ec2-console"\n',
            'GRUB_TERMINAL="console"\n{}\n{}\n'.format(_GRUB_DISTRIBUTOR_OPT, _GRUB_DISABLE_SUBMENU_OPT),
            "Successfully updated /etc/default/grub.",
            True,
            id="al2_replace_ec2_console_add_missing_opts",
        ),
        pytest.param(
            2,
            'GRUB_TERMINAL="console"\n',
            'GRUB_TERMINAL="console"\n{}\n{}\n'.format(_GRUB_DISTRIBUTOR_OPT, _GRUB_DISABLE_SUBMENU_OPT),
            "Successfully updated /etc/default/grub.",
            True,
            id="al2_console_already_set_add_missing_opts",
        ),
        pytest.param(
            2,
            'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR="Amazon Linux"\nGRUB_TERMINAL="ec2-console"\n',
            "GRUB_TIMEOUT=5\n{}\n{}\n{}\n".format(
                _GRUB_DISTRIBUTOR_OPT, 'GRUB_TERMINAL="console"', _GRUB_DISABLE_SUBMENU_OPT
            ),
            "Successfully updated /etc/default/grub.",
            True,
            id="al2_replace_ec2_console_and_existing_distributor",
        ),
        pytest.param(
            2,
            'GRUB_TIMEOUT=5\nGRUB_DISTRIBUTOR="Amazon Linux"\nGRUB_TERMINAL="ec2-console"\n'
            'GRUB_DISABLE_SUBMENU="false"\n',
            "GRUB_TIMEOUT=5\n{}\n{}\n{}\n".format(
                _GRUB_DISTRIBUTOR_OPT, 'GRUB_TERMINAL="console"', _GRUB_DISABLE_SUBMENU_OPT
            ),
            "Successfully updated /etc/default/grub.",
            True,
            id="al2_replace_all_existing_opts",
        ),
    ],
)
def test_fix_grub_settings_on_al2(
    releasever_major, file_content, expected_content, expected_log, expect_write, monkeypatch, caplog
):
    monkeypatch.setattr(
        "convert2rhel.systeminfo.system_info.version",
        namedtuple("Version", ["major"])(releasever_major),
    )
    mock_open = mock.mock_open()
    monkeypatch.setattr(six.moves.builtins, "open", mock_open)
    monkeypatch.setattr("convert2rhel.utils.get_file_content", mock.Mock(return_value=file_content))
    monkeypatch.setattr("convert2rhel.actions.post_conversion.update_grub.backup.backup_control.push", mock.Mock())

    action = update_grub.FixGrubSettingsOnAL2()
    action.run()

    if expect_write:
        mock_open.assert_called_with("/etc/default/grub", "w")
        mock_open().write.assert_called_once_with(expected_content)
    else:
        mock_open.assert_not_called()

    assert expected_log in caplog.text


def test_fix_grub_settings_on_al2_ec2_console_not_found_log(monkeypatch, caplog):
    """Verify the 'not found' log appears when ec2-console is absent but file is still updated with missing opts."""
    monkeypatch.setattr(
        "convert2rhel.systeminfo.system_info.version",
        namedtuple("Version", ["major"])(2),
    )
    monkeypatch.setattr(six.moves.builtins, "open", mock.mock_open())
    monkeypatch.setattr("convert2rhel.utils.get_file_content", mock.Mock(return_value='GRUB_TERMINAL="console"\n'))
    monkeypatch.setattr("convert2rhel.actions.post_conversion.update_grub.backup.backup_control.push", mock.Mock())

    action = update_grub.FixGrubSettingsOnAL2()
    action.run()

    assert 'GRUB_TERMINAL="ec2-console" not found in /etc/default/grub. Nothing to do.' in caplog.text
    assert "Successfully updated /etc/default/grub." in caplog.text
