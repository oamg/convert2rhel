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

import datetime

import pytest
import six

six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))

from convert2rhel import actions, systeminfo
from convert2rhel.actions.system_checks import eus
from convert2rhel.systeminfo import Version, system_info


@pytest.fixture
def eus_action():
    return eus.EusSystemCheck()


class DateMock(datetime.date):
    @classmethod
    def set_today(cls, today_date):
        cls.today_date = today_date

    @classmethod
    def today(cls):
        return cls.today_date


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(eus, "tool_opts", global_tool_opts)


class TestEus:
    @pytest.mark.parametrize(
        ("system_version", "today_date", "message_reported"),
        (
            (Version(7, 9), datetime.date(2024, 12, 4), False),
            (Version(8, 8), datetime.date(2023, 11, 13), False),
            (Version(8, 8), datetime.date(2023, 11, 15), True),
            (Version(9, 2), datetime.date(2024, 12, 4), False),
        ),
    )
    def test_eus_warning_message(
        self, eus_action, monkeypatch, global_tool_opts, system_version, today_date, message_reported, caplog
    ):
        global_tool_opts.eus = False
        monkeypatch.setattr(system_info, "version", system_version)
        monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(eus.datetime, "date", DateMock)
        monkeypatch.setattr(systeminfo, "EUS_MINOR_VERSIONS", {"8.8": "2023-11-14"})
        eus.datetime.date.set_today(today_date)

        eus_action.run()
        expected = {
            actions.ActionMessage(
                level="WARNING",
                id="EUS_COMMAND_LINE_OPTION_UNUSED",
                title="The --eus command line option is unused",
                description="Current system version is under Extended Update Support (EUS). You may want to"
                " consider using the --eus command line option to land on a system patched with the latest"
                " security errata.",
            )
        }

        if message_reported:
            assert expected.issuperset(eus_action.messages)
            assert expected.issubset(eus_action.messages)
        else:
            assert eus_action.messages == []
            "Applicable only when converting the following system versions:\n8.8 after 2023-11-14" in caplog.records[
                -1
            ].message
