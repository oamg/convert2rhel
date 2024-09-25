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

import os

import pytest
import six

from convert2rhel import actions, unit_tests
from convert2rhel.actions.system_checks import tainted_kmods
from convert2rhel.actions.system_checks.tainted_kmods import (
    LINK_KMODS_RH_POLICY,
    LINK_PREVENT_KMODS_FROM_LOADING,
    LINK_TAINTED_KMOD_DOCS,
)


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def tainted_kmods_action():
    return tainted_kmods.TaintedKmods()


@pytest.mark.parametrize(
    ("command_return", "is_error"),
    (
        (("", 0), False),
        (
            (
                (
                    "system76_io 16384 0 - Live 0x0000000000000000 (OE)\n"
                    "system76_acpi 16384 0 - Live 0x0000000000000000 (OE)"
                ),
                0,
            ),
            True,
        ),
    ),
)
def test_check_tainted_kmods(monkeypatch, command_return, is_error, tainted_kmods_action, global_tool_opts):
    run_subprocess_mock = mock.Mock(return_value=command_return)
    monkeypatch.setattr(
        tainted_kmods,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(tainted_kmods, "tool_opts", global_tool_opts)

    tainted_kmods_action.run()

    if is_error:
        unit_tests.assert_actions_result(
            tainted_kmods_action,
            level="OVERRIDABLE",
            id="TAINTED_KMODS_DETECTED",
            title="Tainted kernel modules detected",
            description="Please refer to the diagnosis for further information",
            diagnosis=(
                "Tainted kernel modules detected:\n  system76_io\n  system76_acpi\nThird-party "
                "components are not supported per our software support"
                " policy:\n{}\n".format(LINK_KMODS_RH_POLICY)
            ),
            remediations=(
                "Prevent the modules from loading by following {0}"
                " and run convert2rhel again to continue with the conversion."
                " Although it is not recommended, you can disregard this message by setting the environment variable"
                " 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP' to 1. Overriding this check can be dangerous"
                " so it is recommended that you do a system backup beforehand."
                " For information on what a tainted kernel module is, please refer to this documentation {1}".format(
                    LINK_PREVENT_KMODS_FROM_LOADING, LINK_TAINTED_KMOD_DOCS
                )
            ),
        )


@pytest.mark.parametrize(
    ("command_return", "is_error"),
    (
        (("", 0), False),
        (
            (
                (
                    "system76_io 16384 0 - Live 0x0000000000000000 (OE)\n"
                    "system76_acpi 16384 0 - Live 0x0000000000000000 (OE)"
                ),
                0,
            ),
            True,
        ),
    ),
)
def test_check_tainted_kmods_skip(monkeypatch, command_return, is_error, tainted_kmods_action):
    run_subprocess_mock = mock.Mock(return_value=command_return)
    monkeypatch.setattr(
        tainted_kmods,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(
        os,
        "environ",
        {"CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP": 1},
    )
    tainted_kmods_action.run()

    if is_error:
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="TAINTED_KMODS_DETECTED_MESSAGE",
                    title="Tainted kernel modules detected",
                    description="Please refer to the diagnosis for further information",
                    diagnosis=(
                        "Tainted kernel modules detected:\n  system76_io\n  system76_acpi\nThird-party "
                        "components are not supported per our software support"
                        " policy:\n{}\n".format(LINK_KMODS_RH_POLICY)
                    ),
                    remediations=(
                        "Prevent the modules from loading by following {0}"
                        " and run convert2rhel again to continue with the conversion."
                        " For information on what a tainted kernel module is, please refer to this documentation {1}".format(
                            LINK_PREVENT_KMODS_FROM_LOADING, LINK_TAINTED_KMOD_DOCS
                        )
                    ),
                ),
                actions.ActionMessage(
                    level="WARNING",
                    id="SKIP_TAINTED_KERNEL_MODULE_CHECK",
                    title="Skip tainted kernel module check",
                    description=(
                        "Detected 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP' environment variable, we will skip "
                        "the tainted kernel module check.\n"
                        "Beware, this could leave your system in a broken state."
                    ),
                ),
            )
        )
        assert expected.issuperset(tainted_kmods_action.messages)
        assert expected.issubset(tainted_kmods_action.messages)
