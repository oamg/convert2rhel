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

from convert2rhel import actions, unit_tests
from convert2rhel.actions import tainted_kmods


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
def test_check_tainted_kmods(monkeypatch, command_return, is_error, tainted_kmods_action):
    run_subprocess_mock = mock.Mock(return_value=command_return)
    monkeypatch.setattr(
        actions.tainted_kmods,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    if is_error:
        tainted_kmods_action.run()
        unit_tests.assert_actions_result(
            tainted_kmods_action,
            status="ERROR",
            error_id="TAINTED_KMODS_DETECTED",
            message="Tainted kernel modules detected:\n  system76_io\n",
        )

    else:
        tainted_kmods_action.run()
