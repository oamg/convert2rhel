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

__metaclass__ = type

import pytest
import six

from convert2rhel import actions
from convert2rhel.actions.pre_ponr_changes import special_cases
from convert2rhel.unit_tests import run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos8, oracle8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    (
        "is_iwl7260_installed",
        "is_iwlax2xx_installed",
        "subprocess_output",
        "subprocess_call_count",
        "expected_message",
    ),
    (
        (
            True,
            True,
            ("output", 0),
            1,
            "Removing the iwlax2xx-firmware package. Its content is provided by the RHEL iwl7260-firmware package.",
        ),
        (True, True, ("output", 1), 1, "Unable to remove the package iwlax2xx-firmware."),
        (
            True,
            False,
            ("output", 0),
            0,
            "The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.",
        ),
        (
            False,
            True,
            ("output", 0),
            0,
            "The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.",
        ),
        (
            False,
            False,
            ("output", 0),
            0,
            "The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.",
        ),
    ),
)
@oracle8
def test_remove_iwlax2xx_firmware(
    pretend_os,
    is_iwl7260_installed,
    is_iwlax2xx_installed,
    subprocess_output,
    subprocess_call_count,
    expected_message,
    monkeypatch,
    caplog,
):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("rpm", "-e", "--nodeps", "iwlax2xx-firmware"), subprocess_output),
        )
    )
    is_rpm_installed_mock = mock.Mock(side_effect=[is_iwl7260_installed, is_iwlax2xx_installed])
    monkeypatch.setattr(
        special_cases,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(special_cases.system_info, "is_rpm_installed", value=is_rpm_installed_mock)

    instance = special_cases.RemoveIwlax2xxFirmware()
    instance.run()

    assert run_subprocess_mock.call_count == subprocess_call_count
    assert is_rpm_installed_mock.call_count == 2

    assert expected_message in caplog.records[-1].message
    assert instance.result.level == actions.STATUS_CODE["SUCCESS"]


@centos8
def test_remove_iwlax2xx_firmware_not_ol8(pretend_os, caplog):
    instance = special_cases.RemoveIwlax2xxFirmware()
    instance.run()

    assert "Relevant to Oracle Linux 8 only. Skipping." in caplog.records[-1].message
    assert instance.result.level == actions.STATUS_CODE["SUCCESS"]


@oracle8
@pytest.mark.parametrize(
    (
        "is_iwl7260_installed",
        "is_iwlax2xx_installed",
        "subprocess_output",
        "subprocess_call_count",
    ),
    ((True, True, ("output", 1), 1),),
)
def test_remove_iwlax2xx_firmware_message(
    pretend_os, is_iwl7260_installed, is_iwlax2xx_installed, subprocess_output, subprocess_call_count, monkeypatch
):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("rpm", "-e", "--nodeps", "iwlax2xx-firmware"), subprocess_output),
        )
    )
    is_rpm_installed_mock = mock.Mock(side_effect=[is_iwl7260_installed, is_iwlax2xx_installed])
    monkeypatch.setattr(
        special_cases,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(special_cases.system_info, "is_rpm_installed", value=is_rpm_installed_mock)
    expected = set(
        (
            actions.ActionMessage(
                level="WARNING",
                id="IWLAX2XX_FIRMWARE_REMOVAL_FAILED",
                title="Package removal failed",
                description="Unable to remove the package iwlax2xx-firmware.",
                diagnosis=None,
                remediation=None,
            ),
        )
    )

    instance = special_cases.RemoveIwlax2xxFirmware()
    instance.run()
    assert expected.issuperset(instance.messages)
    assert expected.issubset(instance.messages)
