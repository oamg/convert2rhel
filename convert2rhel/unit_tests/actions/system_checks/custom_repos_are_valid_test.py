# -*- coding: utf-8 -*-
#
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

import unittest

from convert2rhel import actions, unit_tests
from convert2rhel.actions.system_checks import custom_repos_are_valid
from convert2rhel.unit_tests import GetLoggerMocked


class CallYumCmdMocked(unit_tests.MockFunction):
    def __init__(self, ret_code, ret_string):
        self.called = 0
        self.return_code = ret_code
        self.return_string = ret_string
        self.fail_once = False
        self.command = None

    def __call__(self, command, *args, **kwargs):
        if self.fail_once and self.called == 0:
            self.return_code = 1
        if self.fail_once and self.called > 0:
            self.return_code = 0
        self.called += 1
        self.command = command
        return self.return_string, self.return_code


class TestCustomReposAreValid(unittest.TestCase):
    def setUp(self):
        self.custom_repos_are_valid_action = custom_repos_are_valid.CustomReposAreValid()

    @unit_tests.mock(
        custom_repos_are_valid,
        "call_yum_cmd",
        CallYumCmdMocked(ret_code=0, ret_string="Abcdef"),
    )
    @unit_tests.mock(custom_repos_are_valid, "logger", GetLoggerMocked())
    @unit_tests.mock(custom_repos_are_valid.tool_opts, "no_rhsm", True)
    def test_custom_repos_are_valid(self):
        self.custom_repos_are_valid_action.run()
        self.assertEqual(len(custom_repos_are_valid.logger.info_msgs), 1)
        self.assertEqual(len(custom_repos_are_valid.logger.debug_msgs), 1)
        self.assertIn(
            "The repositories passed through the --enablerepo option are all accessible.",
            custom_repos_are_valid.logger.info_msgs,
        )

    @unit_tests.mock(
        custom_repos_are_valid,
        "call_yum_cmd",
        CallYumCmdMocked(ret_code=1, ret_string="YUM/DNF failed"),
    )
    @unit_tests.mock(custom_repos_are_valid, "logger", GetLoggerMocked())
    @unit_tests.mock(custom_repos_are_valid.tool_opts, "no_rhsm", True)
    def test_custom_repos_are_invalid(self):
        self.custom_repos_are_valid_action.run()
        unit_tests.assert_actions_result(
            self.custom_repos_are_valid_action,
            level="ERROR",
            id="UNABLE_TO_ACCESS_REPOSITORIES",
            title="Unable to access repositories",
            description="Access could not be made to the custom repositories.",
            diagnosis="Unable to access the repositories passed through the --enablerepo option.",
            remediation="For more details, see YUM/DNF output:\nYUM/DNF failed",
        )

    @unit_tests.mock(custom_repos_are_valid.tool_opts, "no_rhsm", False)
    def test_custom_repos_are_valid_skip(self):
        self.custom_repos_are_valid_action.run()
        expected = set(
            (
                actions.ActionMessage(
                    level="INFO",
                    id="CUSTOM_REPOSITORIES_ARE_VALID_CHECK_SKIP",
                    title="Skipping the custom repos are valid check",
                    description="Skipping the check of repositories due to the use of RHSM for the conversion.",
                    diagnosis=None,
                    remediation=None,
                ),
            )
        )
        assert expected.issuperset(self.custom_repos_are_valid_action.messages)
        assert expected.issubset(self.custom_repos_are_valid_action.messages)
