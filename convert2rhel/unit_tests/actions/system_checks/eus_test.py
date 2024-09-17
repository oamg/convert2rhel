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

from convert2rhel import actions, pkgmanager, systeminfo
from convert2rhel.actions.system_checks import eus
from convert2rhel.systeminfo import Version, system_info


@pytest.fixture
def eus_action():
    return eus.EusSystemCheck()


class DateMock(datetime.date):
    @classmethod
    def today(cls):
        return cls(2023, 11, 15)


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(eus, "tool_opts", global_tool_opts)


class TestEus:
    @pytest.mark.parametrize(
        ("version_string", "message_reported"),
        (
            (Version(8, 8), True),
            (Version(9, 2), False),  # Change to True after 9.2 is under eus
        ),
    )
    @pytest.mark.skipif(pkgmanager.TYPE != "dnf", reason="el7 systems are not under eus")
    def test_eus_warning_message(self, eus_action, monkeypatch, global_tool_opts, version_string, message_reported):

        global_tool_opts.eus = False
        monkeypatch.setattr(system_info, "version", version_string)
        monkeypatch.setattr(systeminfo, "tool_opts", global_tool_opts)
        monkeypatch.setattr(eus.datetime, "date", DateMock)

        eus_action.run()
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="EUS_COMMAND_LINE_OPTION_UNUSED",
                    title="The --eus command line option is unused",
                    description="Current system version is under Extended Update Support (EUS). You may want to consider using the --eus"
                    " command line option to land on a system patched with the latest security errata.",
                ),
            )
        )

        if message_reported:
            assert expected.issuperset(eus_action.messages)
            assert expected.issubset(eus_action.messages)
        else:
            assert eus_action.messages == []
