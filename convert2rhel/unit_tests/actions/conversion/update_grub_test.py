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
from convert2rhel.actions.conversion import update_grub
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

    update_grub_instance.run()
    if expected is not None:
        assert expected in caplog.records[-1].message


@pytest.mark.parametrize(
    ("config_path", "grub2_mkconfig_exit_code", "grub2_install_exit_code", "expected"),
    (
        (
            "/boot/grub2/grub.cfg",
            1,
            0,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="GRUB2_CONFIG_CREATION_FAILED",
                        title="GRUB2 config file generation failed",
                        description="The GRUB2 config file generation failed.",
                        diagnosis=None,
                        remediations=None,
                    ),
                )
            ),
        ),
        (
            "/boot/grub2/grub.cfg",
            0,
            1,
            set(
                (
                    actions.ActionMessage(
                        level="WARNING",
                        id="GRUB2_INSTALL_FAILED",
                        title="Couldn't install the new images with GRUB2",
                        description="The new images could not be installed with GRUB2.",
                        diagnosis=None,
                        remediations=None,
                    ),
                )
            ),
        ),
    ),
)
def test_update_grub_messages(
    update_grub_instance, monkeypatch, config_path, grub2_mkconfig_exit_code, grub2_install_exit_code, expected
):
    monkeypatch.setattr("convert2rhel.grub.get_grub_device", mock.Mock(return_value="/dev/sda"))
    monkeypatch.setattr(grub, "is_efi", mock.Mock(return_value=False))
    monkeypatch.setattr("convert2rhel.systeminfo.system_info.version", namedtuple("Version", ["major"])(7))
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

    update_grub_instance.run()

    assert expected.issuperset(update_grub_instance.messages)
    assert expected.issubset(update_grub_instance.messages)
