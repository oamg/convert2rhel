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

import datetime

import pytest

from convert2rhel import actions, systeminfo
from convert2rhel.actions.system_checks import els
from convert2rhel.systeminfo import Version, system_info


@pytest.fixture
def els_action():
    return els.ElsSystemCheck()


class DateMock(datetime.date):
    @classmethod
    def today(cls):
        return cls(2024, 6, 13)


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(els, "tool_opts", global_tool_opts)


class TestEus:
    @pytest.mark.parametrize(
        ("version_string", "message_reported"),
        (
            (Version(7, 9), True),
            (Version(8, 8), False),
            (Version(9, 2), False),
        ),
    )
    def test_els_warning_message(
        self, els_action, monkeypatch, global_tool_opts, version_string, message_reported, caplog
    ):
        global_tool_opts.els = False
        monkeypatch.setattr(system_info, "version", version_string)
        monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(els.datetime, "date", DateMock)

        els_action.run()
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="ELS_COMMAND_LINE_OPTION_UNUSED",
                    title="The --els command line option is unused",
                    description="Current system version is under Extended Lifecycle Support (ELS). You may want to"
                    " consider using the --els command line option to land on a system patched with the latest security"
                    " errata.",
                ),
            )
        )

        if message_reported:
            assert expected.issuperset(els_action.messages)
            assert expected.issubset(els_action.messages)
        else:
            assert els_action.messages == []
            "Applicable only to conversions to RHEL 7." in caplog.records[-1].message
