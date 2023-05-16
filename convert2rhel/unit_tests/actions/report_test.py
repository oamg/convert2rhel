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

import re

import pytest

from convert2rhel.actions import STATUS_CODE, report
from convert2rhel.logger import bcolors


#: _LONG_MESSAGE since we do line wrapping
_LONG_MESSAGE = "Will Robinson!  Will Robinson!  Danger Will Robinson...!  Please report directly to your parents in the spaceship immediately.  Danger!  Danger!  Danger!"


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test that all messages are being used with the `include_all_reports`
        # parameter.
        (
            {"PreSubscription": {"status": STATUS_CODE["SUCCESS"], "error_id": None, "message": "All good!"}},
            True,
            ["(SUCCESS) PreSubscription: All good!"],
        ),
        (
            {"PreSubscription": {"status": STATUS_CODE["SUCCESS"], "error_id": None, "message": None}},
            True,
            ["(SUCCESS) PreSubscription: [No further information given]"],
        ),
        (
            {
                "PreSubscription": {"status": STATUS_CODE["SUCCESS"], "error_id": None, "message": "All good!"},
                "PreSubscription2": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "SOME_WARNING",
                    "message": "WARNING MESSAGE",
                },
            },
            True,
            ["(SUCCESS) PreSubscription: All good!", "(WARNING) PreSubscription2.SOME_WARNING: WARNING MESSAGE"],
        ),
        # Test that messages that are below WARNING will not appear in
        # the logs.
        (
            {"PreSubscription": {"status": STATUS_CODE["SUCCESS"], "error_id": None, "message": None}},
            False,
            ["No problems detected during the analysis!"],
        ),
        (
            {
                "PreSubscription": {"status": STATUS_CODE["SUCCESS"], "error_id": None, "message": None},
                "PreSubscription2": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "SOME_WARNING",
                    "message": "WARNING MESSAGE",
                },
            },
            False,
            ["(WARNING) PreSubscription2.SOME_WARNING: WARNING MESSAGE"],
        ),
        # Test all messages are displayed, WARNING and higher
        (
            {
                "PreSubscription1": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "SOME_WARNING",
                    "message": "WARNING MESSAGE",
                },
                "PreSubscription2": {"status": STATUS_CODE["SKIP"], "error_id": "SKIPPED", "message": "SKIP MESSAGE"},
            },
            False,
            [
                "(SKIP) PreSubscription2.SKIPPED: SKIP MESSAGE",
                "(WARNING) PreSubscription1.SOME_WARNING: WARNING MESSAGE",
            ],
        ),
        (
            {
                "WarningAction": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "WARNING",
                    "message": "WARNING MESSAGE",
                },
                "SkipAction": {"status": STATUS_CODE["SKIP"], "error_id": "SKIP", "message": "SKIP MESSAGE"},
                "OverridableAction": {
                    "status": STATUS_CODE["OVERRIDABLE"],
                    "error_id": "OVERRIDABLE",
                    "message": "OVERRIDABLE MESSAGE",
                },
                "ErrorAction": {"status": STATUS_CODE["ERROR"], "error_id": "ERROR", "message": "ERROR MESSAGE"},
                "TestAction": {
                    "status": STATUS_CODE["ERROR"],
                    "error_id": "SECONDERROR",
                    "message": "Test that two of the same status works",
                },
            },
            False,
            [
                "(ERROR) ErrorAction.ERROR: ERROR MESSAGE",
                "(ERROR) TestAction.SECONDERROR: Test that two of the same status works",
                "(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE",
                "(SKIP) SkipAction.SKIP: SKIP MESSAGE",
                "(WARNING) WarningAction.WARNING: WARNING MESSAGE",
            ],
        ),
    ),
)
def test_summary(results, expected_results, include_all_reports, caplog):
    report.summary(results, include_all_reports, with_colors=False)

    for expected in expected_results:
        assert expected in caplog.records[-1].message.splitlines()


def test_summary_with_long_message(caplog):
    """Test a long message because we word wrap those."""
    report.summary(
        {
            "ErrorAction": {
                "status": STATUS_CODE["ERROR"],
                "error_id": "ERROR",
                "message": _LONG_MESSAGE,
            }
        },
        with_colors=False,
    )

    # Word wrapping might break on any spaces so we need to substitute
    # a pattern for those
    pattern = _LONG_MESSAGE.replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test all messages are displayed, WARNING and higher
        (
            {
                "PreSubscription1": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "SOME_WARNING",
                    "message": "WARNING MESSAGE",
                },
                "PreSubscription2": {"status": STATUS_CODE["SKIP"], "error_id": "SKIPPED", "message": "SKIP MESSAGE"},
            },
            False,
            [
                r"\(SKIP\) PreSubscription2.SKIPPED: SKIP MESSAGE",
                r"\(WARNING\) PreSubscription1.SOME_WARNING: WARNING MESSAGE",
            ],
        ),
        (
            {
                "WarningAction": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "WARNING",
                    "message": "WARNING MESSAGE",
                },
                "SkipAction": {"status": STATUS_CODE["SKIP"], "error_id": "SKIP", "message": "SKIP MESSAGE"},
                "OverridableAction": {
                    "status": STATUS_CODE["OVERRIDABLE"],
                    "error_id": "OVERRIDABLE",
                    "message": "OVERRIDABLE MESSAGE",
                },
                "ErrorAction": {"status": STATUS_CODE["ERROR"], "error_id": "ERROR", "message": "ERROR MESSAGE"},
            },
            False,
            [
                r"\(ERROR\) ErrorAction.ERROR: ERROR MESSAGE",
                r"\(OVERRIDABLE\) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE",
                r"\(SKIP\) SkipAction.SKIP: SKIP MESSAGE",
                r"\(WARNING\) WarningAction.WARNING: WARNING MESSAGE",
            ],
        ),
        # Message order with `include_all_reports` set to True.
        (
            {
                "PreSubscription": {"status": STATUS_CODE["SUCCESS"], "error_id": None, "message": "All good!"},
                "WarningAction": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "WARNING",
                    "message": "WARNING MESSAGE",
                },
                "SkipAction": {"status": STATUS_CODE["SKIP"], "error_id": "SKIP", "message": "SKIP MESSAGE"},
                "OverridableAction": {
                    "status": STATUS_CODE["OVERRIDABLE"],
                    "error_id": "OVERRIDABLE",
                    "message": "OVERRIDABLE MESSAGE",
                },
                "ErrorAction": {"status": STATUS_CODE["ERROR"], "error_id": "ERROR", "message": "ERROR MESSAGE"},
            },
            True,
            [
                r"\(ERROR\) ErrorAction.ERROR: ERROR MESSAGE",
                r"\(OVERRIDABLE\) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE",
                r"\(SKIP\) SkipAction.SKIP: SKIP MESSAGE",
                r"\(WARNING\) WarningAction.WARNING: WARNING MESSAGE",
                r"\(SUCCESS\) PreSubscription: All good!",
            ],
        ),
    ),
)
def test_summary_ordering(results, include_all_reports, expected_results, caplog):

    report.summary(results, include_all_reports, with_colors=False)

    # Prove that all the messages occurred and in the right order.
    message = caplog.records[-1].message

    pattern = []
    for entry in expected_results:
        pattern.append(entry)
    pattern = ".*".join(pattern)

    assert re.search(pattern, message, re.DOTALL)


@pytest.mark.parametrize(
    ("results", "expected"),
    (
        (
            {"ErrorAction": dict(status=STATUS_CODE["ERROR"], error_id="ERROR", message="ERROR MESSAGE")},
            "%s(ERROR) ErrorAction.ERROR: ERROR MESSAGE%s" % (bcolors.FAIL, bcolors.ENDC),
        ),
        (
            {
                "OverridableAction": dict(
                    status=STATUS_CODE["OVERRIDABLE"], error_id="OVERRIDABLE", message="OVERRIDABLE MESSAGE"
                )
            },
            "%s(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE%s" % (bcolors.FAIL, bcolors.ENDC),
        ),
        (
            {"SkipAction": dict(status=STATUS_CODE["SKIP"], error_id="SKIP", message="SKIP MESSAGE")},
            "%s(SKIP) SkipAction.SKIP: SKIP MESSAGE%s" % (bcolors.FAIL, bcolors.ENDC),
        ),
        (
            {"WarningAction": dict(status=STATUS_CODE["WARNING"], error_id="WARNING", message="WARNING MESSAGE")},
            "%s(WARNING) WarningAction.WARNING: WARNING MESSAGE%s" % (bcolors.WARNING, bcolors.ENDC),
        ),
        (
            {
                "SuccessfulAction": dict(
                    status=STATUS_CODE["SUCCESS"], error_id="SUCCESSFUL", message="SUCCESSFUL MESSAGE"
                )
            },
            "%s(SUCCESS) SuccessfulAction.SUCCESSFUL: SUCCESSFUL MESSAGE%s" % (bcolors.OKGREEN, bcolors.ENDC),
        ),
    ),
)
def test_summary_colors(results, expected, caplog):
    report.summary(results, include_all_reports=True, with_colors=True)
    assert expected in caplog.records[-1].message
