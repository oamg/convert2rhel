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

import json
import os.path
import re

import pytest

from convert2rhel.actions import STATUS_CODE, report
from convert2rhel.logger import bcolors


#: _LONG_MESSAGE since we do line wrapping
_LONG_MESSAGE = "Will Robinson!  Will Robinson!  Danger Will Robinson...!  Please report directly to your parents in the spaceship immediately.  Danger!  Danger!  Danger!"


@pytest.mark.parametrize(
    ("results", "expected"),
    (
        (
            {
                "CONVERT2RHEL_LATEST_VERSION": {
                    "result": dict(level=STATUS_CODE["SUCCESS"]),
                    "messages": [
                        dict(level=STATUS_CODE["WARNING"], id="WARNING_ONE", message="A warning message"),
                    ],
                },
            },
            {
                "format_version": "1.0",
                "actions": {
                    "CONVERT2RHEL_LATEST_VERSION": {
                        "result": dict(level="SUCCESS"),
                        "messages": [
                            dict(level="WARNING", id="WARNING_ONE", message="A warning message"),
                        ],
                    },
                },
            },
        ),
    ),
)
def test_summary_as_json(results, expected, tmpdir):
    """Test that the results that we're given are what is written to the json log file."""
    json_report_file = os.path.join(str(tmpdir), "c2r-assessment.json")

    report.summary_as_json(results, json_report_file)

    with open(json_report_file, "r") as f:
        file_contents = json.load(f)

    assert file_contents == expected


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test that all messages are being used with the `include_all_reports`
        # parameter.
        (
            {
                "PreSubscription": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": "All good!"},
                )
            },
            True,
            ["(WARNING) PreSubscription::WARNING_ID - WARNING MESSAGE", "(SUCCESS) PreSubscription - All good!"],
        ),
        (
            {
                "PreSubscription": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": None},
                )
            },
            True,
            [
                "(WARNING) PreSubscription::WARNING_ID - WARNING MESSAGE",
                "(SUCCESS) PreSubscription - [No further information given]",
            ],
        ),
        (
            {
                "PreSubscription": dict(
                    messages=[], result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": "All good!"}
                ),
                "PreSubscription2": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "message": "SKIP MESSAGE",
                    },
                ),
            },
            True,
            [
                "(SUCCESS) PreSubscription - All good!",
                "(WARNING) PreSubscription2::WARNING_ID - WARNING MESSAGE",
                "(SKIP) PreSubscription2::SKIPPED - SKIP MESSAGE",
            ],
        ),
        # Test that messages that are below WARNING will not appear in
        # the logs.
        (
            {
                "PreSubscription": dict(
                    messages=[], result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": None}
                )
            },
            False,
            ["No problems detected during the analysis!"],
        ),
        (
            {
                "PreSubscription": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": None},
                )
            },
            False,
            ["(WARNING) PreSubscription::WARNING_ID - WARNING MESSAGE"],
        ),
        (
            {
                "PreSubscription": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 1"}],
                    result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": None},
                ),
                "PreSubscription2": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 2"}],
                    result={
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "message": "SKIP MESSAGE",
                    },
                ),
            },
            False,
            [
                "(SKIP) PreSubscription2::SKIPPED - SKIP MESSAGE",
                "(WARNING) PreSubscription::WARNING_ID - WARNING MESSAGE 1",
                "(WARNING) PreSubscription2::WARNING_ID - WARNING MESSAGE 2",
            ],
        ),
        # Test all messages are displayed, SKIP and higher
        (
            {
                "PreSubscription1": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 1"}],
                    result={
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "message": "SKIP MESSAGE",
                    },
                ),
                "PreSubscription2": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 2"}],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE_ID",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
            },
            False,
            [
                "(OVERRIDABLE) PreSubscription2::OVERRIDABLE_ID - OVERRIDABLE MESSAGE",
                "(SKIP) PreSubscription1::SKIPPED - SKIP MESSAGE",
                "(WARNING) PreSubscription1::WARNING_ID - WARNING MESSAGE 1",
                "(WARNING) PreSubscription2::WARNING_ID - WARNING MESSAGE 2",
            ],
        ),
        (
            {
                "SkipAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 4"}],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIP", "message": "SKIP MESSAGE"},
                ),
                "OverridableAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 3"}],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
                "ErrorAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 2"}],
                    result={"level": STATUS_CODE["ERROR"], "id": "ERROR", "message": "ERROR MESSAGE"},
                ),
                "TestAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 1"}],
                    result={
                        "level": STATUS_CODE["ERROR"],
                        "id": "SECONDERROR",
                        "message": "Test that two of the same level works",
                    },
                ),
            },
            False,
            [
                "(ERROR) ErrorAction::ERROR - ERROR MESSAGE",
                "(ERROR) TestAction::SECONDERROR - Test that two of the same level works",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - OVERRIDABLE MESSAGE",
                "(SKIP) SkipAction::SKIP - SKIP MESSAGE",
                "(WARNING) SkipAction::WARNING_ID - WARNING MESSAGE 4",
                "(WARNING) OverridableAction::WARNING_ID - WARNING MESSAGE 3",
                "(WARNING) ErrorAction::WARNING_ID - WARNING MESSAGE 2",
                "(WARNING) TestAction::WARNING_ID - WARNING MESSAGE 1",
            ],
        ),
    ),
)
def test_summary(results, expected_results, include_all_reports, caplog):
    report.summary(results, include_all_reports, with_colors=False)

    for expected in expected_results:
        assert expected in caplog.records[-1].message.splitlines()


def test_results_summary_with_long_message(caplog):
    """Test a long message because we word wrap those."""
    report.summary(
        {
            "ErrorAction": dict(
                messages=[],
                result={
                    "level": STATUS_CODE["ERROR"],
                    "id": "ERROR",
                    "message": _LONG_MESSAGE,
                },
            )
        },
        with_colors=False,
    )

    # Word wrapping might break on any spaces so we need to substitute
    # a pattern for those
    pattern = _LONG_MESSAGE.replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)


def test_messages_summary_with_long_message(caplog):
    """Test a long message because we word wrap those."""
    report.summary(
        {
            "ErrorAction": dict(
                messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": _LONG_MESSAGE}],
                result={"level": STATUS_CODE["SUCCESS"], "id": "", "message": ""},
            )
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
        # Test all messages are displayed, SKIP and higher
        (
            {
                "PreSubscription2": dict(
                    messages=[],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIPPED", "message": "SKIP MESSAGE"},
                ),
                "PreSubscription1": dict(
                    messages=[],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "SOME_OVERRIDABLE",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
            },
            False,
            [
                r"\(OVERRIDABLE\) PreSubscription1::SOME_OVERRIDABLE - OVERRIDABLE MESSAGE",
                r"\(SKIP\) PreSubscription2::SKIPPED - SKIP MESSAGE",
            ],
        ),
        (
            {
                "SkipAction": dict(
                    messages=[],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIP", "message": "SKIP MESSAGE"},
                ),
                "OverridableAction": dict(
                    messages=[],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
                "ErrorAction": dict(
                    messages=[],
                    result={"level": STATUS_CODE["ERROR"], "id": "ERROR", "message": "ERROR MESSAGE"},
                ),
            },
            False,
            [
                r"\(ERROR\) ErrorAction::ERROR - ERROR MESSAGE",
                r"\(OVERRIDABLE\) OverridableAction::OVERRIDABLE - OVERRIDABLE MESSAGE",
                r"\(SKIP\) SkipAction::SKIP - SKIP MESSAGE",
            ],
        ),
        # Message order with `include_all_reports` set to True.
        (
            {
                "PreSubscription": dict(
                    messages=[],
                    result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": "All good!"},
                ),
                "SkipAction": dict(
                    messages=[],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIP", "message": "SKIP MESSAGE"},
                ),
                "OverridableAction": dict(
                    messages=[],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
                "ErrorAction": dict(
                    messages=[],
                    result={"level": STATUS_CODE["ERROR"], "id": "ERROR", "message": "ERROR MESSAGE"},
                ),
            },
            True,
            [
                r"\(ERROR\) ErrorAction::ERROR - ERROR MESSAGE",
                r"\(OVERRIDABLE\) OverridableAction::OVERRIDABLE - OVERRIDABLE MESSAGE",
                r"\(SKIP\) SkipAction::SKIP - SKIP MESSAGE",
                r"\(SUCCESS\) PreSubscription - All good!",
            ],
        ),
    ),
)
def test_results_summary_ordering(results, include_all_reports, expected_results, caplog):

    report.summary(results, include_all_reports, with_colors=False)

    # Prove that all the messages occurred and in the right order.
    message = caplog.records[-1].message

    pattern = []
    for entry in expected_results:
        pattern.append(entry)
    pattern = ".*".join(pattern)

    assert re.search(pattern, message, re.DOTALL)


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test all messages are displayed, SKIP and higher
        (
            {
                "PreSubscription2": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIPPED", "message": "SKIP MESSAGE"},
                ),
                "PreSubscription1": dict(
                    messages=[],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "SOME_OVERRIDABLE",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
            },
            False,
            [
                "(OVERRIDABLE) PreSubscription1::SOME_OVERRIDABLE - OVERRIDABLE MESSAGE",
                "(SKIP) PreSubscription2::SKIPPED - SKIP MESSAGE",
                "(WARNING) PreSubscription2::WARNING_ID - WARNING MESSAGE",
            ],
        ),
        (
            {
                "SkipAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 1"}],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIP", "message": "SKIP MESSAGE"},
                ),
                "OverridableAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 2"}],
                    result={
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "message": "OVERRIDABLE MESSAGE",
                    },
                ),
                "ErrorAction": dict(
                    messages=[],
                    result={"level": STATUS_CODE["ERROR"], "id": "ERROR", "message": "ERROR MESSAGE"},
                ),
            },
            False,
            [
                "(ERROR) ErrorAction::ERROR - ERROR MESSAGE",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - OVERRIDABLE MESSAGE",
                "(SKIP) SkipAction::SKIP - SKIP MESSAGE",
                "(WARNING) SkipAction::WARNING_ID - WARNING MESSAGE 1",
                "(WARNING) OverridableAction::WARNING_ID - WARNING MESSAGE 2",
            ],
        ),
        # Message order with `include_all_reports` set to True.
        (
            {
                "PreSubscription": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 1"}],
                    result={"level": STATUS_CODE["SUCCESS"], "id": None, "message": "All good!"},
                ),
                "SkipAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 2"}],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIP", "message": "SKIP MESSAGE"},
                ),
                "OverridableAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 3"}],
                    result={"level": STATUS_CODE["OVERRIDABLE"], "id": "OVERRIDABLE", "message": "OVERRIDABLE MESSAGE"},
                ),
                "ErrorAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE 4"}],
                    result={"level": STATUS_CODE["ERROR"], "id": "ERROR", "message": "ERROR MESSAGE"},
                ),
            },
            True,
            [
                "(ERROR) ErrorAction::ERROR - ERROR MESSAGE",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - OVERRIDABLE MESSAGE",
                "(SKIP) SkipAction::SKIP - SKIP MESSAGE",
                "(WARNING) PreSubscription::WARNING_ID - WARNING MESSAGE 1",
                "(WARNING) SkipAction::WARNING_ID - WARNING MESSAGE 2",
                "(WARNING) OverridableAction::WARNING_ID - WARNING MESSAGE 3",
                "(WARNING) ErrorAction::WARNING_ID - WARNING MESSAGE 4",
                "(SUCCESS) PreSubscription - All good!",
            ],
        ),
    ),
)
def test_messages_summary_ordering(results, include_all_reports, expected_results, caplog):

    report.summary(results, include_all_reports, with_colors=False)

    # Filter informational messages and empty strings out of message.splitlines
    caplog_messages = []
    for message in caplog.records[1].message.splitlines():
        if not message.startswith("==========") and not message == "":
            caplog_messages.append(message)

    # Prove that all the messages occurred
    for expected in expected_results:
        assert expected in caplog_messages

    assert len(expected_results) == len(caplog_messages)


@pytest.mark.parametrize(
    ("results", "expected_result", "expected_message"),
    (
        (
            {
                "ErrorAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["ERROR"], "id": "ERROR", "message": "ERROR MESSAGE"},
                )
            },
            "%s(ERROR) ErrorAction::ERROR - ERROR MESSAGE%s" % (bcolors.FAIL, bcolors.ENDC),
            "%s(WARNING) ErrorAction::WARNING_ID - WARNING MESSAGE%s" % (bcolors.WARNING, bcolors.ENDC),
        ),
        (
            {
                "OverridableAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["OVERRIDABLE"], "id": "OVERRIDABLE", "message": "OVERRIDABLE MESSAGE"},
                )
            },
            "%s(OVERRIDABLE) OverridableAction::OVERRIDABLE - OVERRIDABLE MESSAGE%s" % (bcolors.FAIL, bcolors.ENDC),
            "%s(WARNING) OverridableAction::WARNING_ID - WARNING MESSAGE%s" % (bcolors.WARNING, bcolors.ENDC),
        ),
        (
            {
                "SkipAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["SKIP"], "id": "SKIP", "message": "SKIP MESSAGE"},
                )
            },
            "%s(SKIP) SkipAction::SKIP - SKIP MESSAGE%s" % (bcolors.FAIL, bcolors.ENDC),
            "%s(WARNING) SkipAction::WARNING_ID - WARNING MESSAGE%s" % (bcolors.WARNING, bcolors.ENDC),
        ),
        (
            {
                "SuccessfulAction": dict(
                    messages=[{"level": STATUS_CODE["WARNING"], "id": "WARNING_ID", "message": "WARNING MESSAGE"}],
                    result={"level": STATUS_CODE["SUCCESS"], "id": "SUCCESSFUL", "message": "SUCCESSFUL MESSAGE"},
                )
            },
            "%s(SUCCESS) SuccessfulAction::SUCCESSFUL - SUCCESSFUL MESSAGE%s" % (bcolors.OKGREEN, bcolors.ENDC),
            "%s(WARNING) SuccessfulAction::WARNING_ID - WARNING MESSAGE%s" % (bcolors.WARNING, bcolors.ENDC),
        ),
    ),
)
def test_summary_colors(results, expected_result, expected_message, caplog):
    report.summary(results, include_all_reports=True, with_colors=True)
    assert expected_result in caplog.records[-1].message
    assert expected_message in caplog.records[-1].message
