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

from convert2rhel import actions, toolopts
from convert2rhel.actions.system_checks import payg
from convert2rhel.systeminfo import Version, system_info


@pytest.fixture
def payg_action():
    return payg.PaygSystemCheck()


class TestPayg:
    @pytest.mark.parametrize(
        ("payg_set", "version_string", "message_reported"),
        (
            (False, Version(7, 9), False),
            (False, Version(8, 6), False),
            (False, Version(8, 8), False),
            (False, Version(9, 2), False),
            (False, Version(9, 3), False),
            (True, Version(7, 9), False),
            (True, Version(8, 6), True),
            (True, Version(8, 8), True),
            (True, Version(9, 2), True),
            (True, Version(9, 3), True),
        ),
    )
    def test_eus_warning_message(self, payg_action, monkeypatch, payg_set, version_string, message_reported):

        monkeypatch.setattr(toolopts.tool_opts, "payg", payg_set)
        monkeypatch.setattr(system_info, "version", version_string)

        payg_action.run()
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="PAYG_COMMAND_LINE_OPTION_UNSUPPORTED",
                    title="The --payg option is unsupported on this system version",
                    description="The --payg command line option is supported only on RHEL 7.",
                    remediation="Run convert2rhel without --payg option.",
                ),
            )
        )

        if message_reported:
            assert expected.issuperset(payg_action.messages)
            assert expected.issubset(payg_action.messages)
        else:
            assert payg_action.messages == []
