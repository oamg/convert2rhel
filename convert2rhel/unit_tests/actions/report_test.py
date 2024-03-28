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
import six

from convert2rhel.actions import STATUS_CODE, report
from convert2rhel.logger import bcolors


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


#: _LONG_MESSAGE since we do line wrapping
_LONG_MESSAGE = {
    "title": "Will Robinson! Will Robinson!",
    "description": " Danger Will Robinson...!",
    "diagnosis": " Danger! Danger! Danger!",
    "remediations": " Please report directly to your parents in the spaceship immediately.",
    "variables": {},
}


@pytest.mark.parametrize(
    ("results", "expected"),
    (
        (
            {
                "CONVERT2RHEL_LATEST_VERSION": {
                    "result": {"level": STATUS_CODE["SUCCESS"], "id": "SUCCESS"},
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ONE",
                            "title": "A warning message",
                            "description": "",
                            "diagnosis": "",
                            "remediations": "",
                        },
                    ],
                },
            },
            {
                "format_version": "1.1",
                "status": "WARNING",
                "actions": {
                    "CONVERT2RHEL_LATEST_VERSION": {
                        "result": {"level": "SUCCESS", "id": "SUCCESS"},
                        "messages": [
                            {
                                "level": "WARNING",
                                "id": "WARNING_ONE",
                                "title": "A warning message",
                                "description": "",
                                "diagnosis": "",
                                "remediations": "",
                            },
                        ],
                    },
                },
            },
        ),
        (
            {
                "CONVERT2RHEL_LATEST_VERSION": {
                    "result": {"level": STATUS_CODE["SUCCESS"], "id": "SUCCESS"},
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ONE",
                            "title": "A warning message",
                            "description": "A description",
                            "diagnosis": "A diagnosis",
                            "remediations": "A remediations",
                        },
                    ],
                },
            },
            {
                "format_version": "1.1",
                "status": "WARNING",
                "actions": {
                    "CONVERT2RHEL_LATEST_VERSION": {
                        "result": {"level": "SUCCESS", "id": "SUCCESS"},
                        "messages": [
                            {
                                "level": "WARNING",
                                "id": "WARNING_ONE",
                                "title": "A warning message",
                                "description": "A description",
                                "diagnosis": "A diagnosis",
                                "remediations": "A remediations",
                            },
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
                "PreSubscription": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                }
            },
            True,
            [
                "(WARNING) PreSubscription::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(SUCCESS) PreSubscription::SUCCESS - N/A",
            ],
        ),
        # Post conversion
        (
            {
                "PreSubscription": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                }
            },
            True,
            [
                "(WARNING) PreSubscription::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(SUCCESS) PreSubscription::SUCCESS - N/A",
            ],
        ),
        (
            {
                "PreSubscription": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "PreSubscription2": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            True,
            [
                "(SUCCESS) PreSubscription::SUCCESS - N/A",
                "(WARNING) PreSubscription2::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(SKIP) PreSubscription2::SKIPPED - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
            ],
        ),
        # Test that messages that are below WARNING will not appear in
        # the logs.
        (
            {
                "PreSubscription": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                }
            },
            False,
            ["No problems detected!"],
        ),
        (
            {
                "PreSubscription": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                }
            },
            False,
            [
                "(WARNING) PreSubscription::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on"
            ],
        ),
        (
            {
                "PreSubscription": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "PreSubscription2": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                "(SKIP) PreSubscription2::SKIPPED - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) PreSubscription::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) PreSubscription2::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
            ],
        ),
        # Test all messages are displayed, SKIP and higher
        (
            {
                "PreSubscription1": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "PreSubscription2": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE_ID",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                "(OVERRIDABLE) PreSubscription2::OVERRIDABLE_ID - Overridable\n     Description: Action overridable\n     Diagnosis: User overridable\n     Remediations: move on",
                "(SKIP) PreSubscription1::SKIPPED - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) PreSubscription1::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) PreSubscription2::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
            ],
        ),
        (
            {
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "TestAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "SECONDERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                "(ERROR) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
                "(ERROR) TestAction::SECONDERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action overridable\n     Diagnosis: User overridable\n     Remediations: move on",
                "(SKIP) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) SkipAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) OverridableAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) ErrorAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) TestAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
            ],
        ),
    ),
)
def test_summary(results, expected_results, include_all_reports, caplog):
    report._summary(results, include_all_reports, disable_colors=True)

    for expected in expected_results:
        assert expected in caplog.records[-1].message


@pytest.mark.parametrize(
    ("long_message"),
    (
        (_LONG_MESSAGE),
        (
            {
                "title": "Will Robinson! Will Robinson!",
                "description": " Danger Will Robinson...!" * 8,
                "diagnosis": " Danger!" * 15,
                "remediations": " Please report directly to your parents in the spaceship immediately." * 2,
                "variables": {},
            }
        ),
    ),
)
def test_results_summary_with_long_message(long_message, caplog):
    """Test a long message because we word wrap those."""
    result = {"level": STATUS_CODE["ERROR"], "id": "ERROR"}
    result.update(long_message)
    report._summary(
        {
            "ErrorAction": {
                "messages": [],
                "result": result,
            }
        },
        include_all_reports=False,
        disable_colors=True,
    )

    # Word wrapping might break on any spaces so we need to substitute
    # a pattern for those
    pattern = long_message["title"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)

    pattern = long_message["description"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)

    pattern = long_message["diagnosis"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)

    pattern = long_message["remediations"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)


@pytest.mark.parametrize(
    ("long_message"),
    (
        (_LONG_MESSAGE),
        (
            {
                "title": "Will Robinson! Will Robinson!",
                "description": " Danger Will Robinson...!" * 8,
                "diagnosis": " Danger!" * 15,
                "remediations": " Please report directly to your parents in the spaceship immediately." * 2,
                "variables": {},
            }
        ),
    ),
)
def test_messages_summary_with_long_message(long_message, caplog):
    """Test a long message because we word wrap those."""
    messages = {"level": STATUS_CODE["WARNING"], "id": "WARNING_ID"}
    messages.update(long_message)
    report._summary(
        {
            "ErrorAction": {
                "messages": [messages],
                "result": {
                    "level": STATUS_CODE["SUCCESS"],
                    "id": "",
                    "title": "",
                    "description": "",
                    "diagnosis": "",
                    "remediations": "",
                    "variables": {},
                },
            }
        },
        include_all_reports=False,
        disable_colors=True,
    )

    # Word wrapping might break on any spaces so we need to substitute
    # a pattern for those
    pattern = long_message["title"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)

    pattern = long_message["description"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)

    pattern = long_message["diagnosis"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)

    pattern = long_message["remediations"].replace(" ", "[ \t\n]+")
    assert re.search(pattern, caplog.records[-1].message)


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test all messages are displayed, SKIP and higher
        (
            {
                "PreSubscription2": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "title": "Skipped",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "PreSubscription1": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "SOME_OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action override",
                        "diagnosis": "User override",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                r"\(SKIP\) PreSubscription2::SKIPPED - Skipped\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                r"\(OVERRIDABLE\) PreSubscription1::SOME_OVERRIDABLE - Overridable\n     Description: Action override\n     Diagnosis: User override\n     Remediations: move on",
            ],
        ),
        (
            {
                "SkipAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action override",
                        "diagnosis": "User override",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                r"\(SKIP\) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                r"\(OVERRIDABLE\) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action override\n     Diagnosis: User override\n     Remediations: move on",
                r"\(ERROR\) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
            ],
        ),
        # Message order with `include_all_reports` set to True.
        (
            {
                "PreSubscription": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "SkipAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action override",
                        "diagnosis": "User override",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            True,
            [
                r"\(SUCCESS\) PreSubscription::SUCCESS - N/A",
                r"\(SKIP\) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                r"\(OVERRIDABLE\) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action override\n     Diagnosis: User override\n     Remediations: move on",
                r"\(ERROR\) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
            ],
        ),
        # Post conversion
        (
            {
                "PreSubscription": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "SkipAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action override",
                        "diagnosis": "User override",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            True,
            [
                r"\(SUCCESS\) PreSubscription::SUCCESS - N/A",
                r"\(SKIP\) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                r"\(OVERRIDABLE\) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action override\n     Diagnosis: User override\n     Remediations: move on",
                r"\(ERROR\) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
            ],
        ),
    ),
)
def test_results_summary_ordering(results, include_all_reports, expected_results, caplog):
    report._summary(results, include_all_reports, disable_colors=True)

    # Prove that all the messages occurred and in the right order.
    message = caplog.records[-1].message

    pattern = []
    for entry in expected_results:
        pattern.append(entry)
    pattern = ".*".join(pattern)

    assert re.search(pattern, message, re.DOTALL | re.MULTILINE)


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test all messages are displayed, SKIP and higher
        (
            {
                "PreSubscription2": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIPPED",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "PreSubscription1": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "SOME_OVERRIDABLE",
                        "title": "Override",
                        "description": "Action override",
                        "diagnosis": "User override",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                "(OVERRIDABLE) PreSubscription1::SOME_OVERRIDABLE - Override\n     Description: Action override\n     Diagnosis: User override\n     Remediations: move on",
                "(SKIP) PreSubscription2::SKIPPED - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) PreSubscription2::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
            ],
        ),
        (
            {
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            False,
            [
                "(ERROR) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action overridable\n     Diagnosis: User overridable\n     Remediations: move on",
                "(SKIP) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) SkipAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) OverridableAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
            ],
        ),
        # Message order with `include_all_reports` set to True.
        (
            {
                "PreSubscription": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            True,
            [
                "(ERROR) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action overridable\n     Diagnosis: User overridable\n     Remediations: move on",
                "(SKIP) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) PreSubscription::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) SkipAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) OverridableAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) ErrorAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(SUCCESS) PreSubscription::SUCCESS - N/A",
            ],
        ),
        # Post conversion
        (
            {
                "PreSubscription": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            True,
            [
                "(ERROR) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on",
                "(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action overridable\n     Diagnosis: User overridable\n     Remediations: move on",
                "(SKIP) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on",
                "(WARNING) PreSubscription::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) SkipAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) OverridableAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(WARNING) ErrorAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on",
                "(SUCCESS) PreSubscription::SUCCESS - N/A",
            ],
        ),
    ),
)
def test_messages_summary_ordering(results, include_all_reports, expected_results, caplog):
    report._summary(results, include_all_reports=include_all_reports, disable_colors=True)

    # Filter informational messages and empty strings out of message.splitlines
    caplog_messages = []
    for message in caplog.records[0].message.splitlines():
        if not message.startswith("==========") and not message == "":
            caplog_messages.append(message)

    # Prove that all the messages occurred
    for expected in expected_results:
        message = "\n".join(caplog_messages)
        assert expected in message


@pytest.mark.parametrize(
    ("results", "expected_result", "expected_message"),
    (
        (
            {
                "ErrorAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                }
            },
            "{begin}(ERROR) ErrorAction::ERROR - Error\n     Description: Action error\n     Diagnosis: User error\n     Remediations: move on{end}".format(
                begin=bcolors.FAIL, end=bcolors.ENDC
            ),
            "{begin}(WARNING) ErrorAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on{end}".format(
                begin=bcolors.WARNING, end=bcolors.ENDC
            ),
        ),
        (
            {
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                }
            },
            "{begin}(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n     Description: Action overridable\n     Diagnosis: User overridable\n     Remediations: move on{end}".format(
                begin=bcolors.FAIL, end=bcolors.ENDC
            ),
            "{begin}(WARNING) OverridableAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on{end}".format(
                begin=bcolors.WARNING, end=bcolors.ENDC
            ),
        ),
        (
            {
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                }
            },
            "{begin}(SKIP) SkipAction::SKIP - Skip\n     Description: Action skip\n     Diagnosis: User skip\n     Remediations: move on{end}".format(
                begin=bcolors.FAIL, end=bcolors.ENDC
            ),
            "{begin}(WARNING) SkipAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on{end}".format(
                begin=bcolors.WARNING, end=bcolors.ENDC
            ),
        ),
        (
            {
                "SuccessfulAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SUCCESS"],
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                }
            },
            "{begin}(SUCCESS) SuccessfulAction::SUCCESS - N/A{end}".format(begin=bcolors.OKGREEN, end=bcolors.ENDC),
            "{begin}(WARNING) SuccessfulAction::WARNING_ID - Warning\n     Description: Action warning\n     Diagnosis: User warning\n     Remediations: move on{end}".format(
                begin=bcolors.WARNING, end=bcolors.ENDC
            ),
        ),
    ),
)
def test_summary_colors(results, expected_result, expected_message, caplog):
    report._summary(results, include_all_reports=True, disable_colors=False)
    assert expected_result in caplog.records[-1].message
    assert expected_message in caplog.records[-1].message


@pytest.mark.parametrize(
    ("results", "text_lines"),
    (
        (
            {
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "TestAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "SECONDERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            [
                "{begin_fail}(ERROR) ErrorAction::ERROR - Error\n Description: Action error\n Diagnosis: User error\n Remediations: move on\n{end}",
                "{begin_fail}(ERROR) TestAction::SECONDERROR - Error\n Description: Action error\n Diagnosis: User error\n Remediations: move on\n{end}",
                "{begin_fail}(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n Description: Action overridable\n Diagnosis: User overridable\n Remediations: move on\n{end}",
                "{begin_fail}(SKIP) SkipAction::SKIP - Skip\n Description: Action skip\n Diagnosis: User skip\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) SkipAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) OverridableAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) ErrorAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) TestAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
            ],
        ),
    ),
)
def test_summary_as_txt(results, text_lines, tmpdir):
    convert2rhel_txt_results = tmpdir.join("convert2rhel-pre-conversion.txt")
    report.summary_as_txt(results, str(convert2rhel_txt_results))

    for expected in text_lines:
        assert (
            expected.format(begin_fail=bcolors.FAIL, begin_warning=bcolors.WARNING, end=bcolors.ENDC)
            in convert2rhel_txt_results.read()
        )
    assert "test" not in convert2rhel_txt_results.read()


@pytest.mark.parametrize(
    ("results", "text_lines"),
    (
        (
            {
                "SkipAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["SKIP"],
                        "id": "SKIP",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "OverridableAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["OVERRIDABLE"],
                        "id": "OVERRIDABLE",
                        "title": "Overridable",
                        "description": "Action overridable",
                        "diagnosis": "User overridable",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "ErrorAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "ERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
                "TestAction": {
                    "messages": [
                        {
                            "level": STATUS_CODE["WARNING"],
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": STATUS_CODE["ERROR"],
                        "id": "SECONDERROR",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            [
                "{begin_fail}(ERROR) ErrorAction::ERROR - Error\n Description: Action error\n Diagnosis: User error\n Remediations: move on\n{end}",
                "{begin_fail}(ERROR) TestAction::SECONDERROR - Error\n Description: Action error\n Diagnosis: User error\n Remediations: move on\n{end}",
                "{begin_fail}(OVERRIDABLE) OverridableAction::OVERRIDABLE - Overridable\n Description: Action overridable\n Diagnosis: User overridable\n Remediations: move on\n{end}",
                "{begin_fail}(SKIP) SkipAction::SKIP - Skip\n Description: Action skip\n Diagnosis: User skip\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) SkipAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) OverridableAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) ErrorAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
                "{begin_warning}(WARNING) TestAction::WARNING_ID - Warning\n Description: Action warning\n Diagnosis: User warning\n Remediations: move on\n{end}",
            ],
        ),
    ),
)
def test_summary_as_txt_file_exists(results, text_lines, tmpdir):
    convert2rhel_txt_results = tmpdir.join("convert2rhel-pre-conversion.txt")
    convert2rhel_txt_results.write("test")
    report.summary_as_txt(results, str(convert2rhel_txt_results))

    for expected in text_lines:
        assert (
            expected.format(begin_fail=bcolors.FAIL, begin_warning=bcolors.WARNING, end=bcolors.ENDC)
            in convert2rhel_txt_results.read()
        )
    assert "test" not in convert2rhel_txt_results.read()


@pytest.mark.parametrize(
    ("results", "expected"),
    (
        (
            {
                "PreSubscription": {
                    "messages": [
                        {
                            "level": 51,
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": 0,
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                }
            },
            {
                ("PreSubscription", "SUCCESS"): {
                    "level": 0,
                    "title": "",
                    "description": "",
                    "remediations": "",
                    "diagnosis": "",
                    "variables": {},
                },
                ("PreSubscription", "WARNING_ID"): {
                    "level": 51,
                    "title": "Warning",
                    "description": "Action warning",
                    "remediations": "move on",
                    "diagnosis": "User warning",
                    "variables": {},
                },
            },
        ),
        (
            {
                "PreSubscription": {
                    "messages": [],
                    "result": {
                        "level": 0,
                        "id": "SUCCESS",
                        "title": "",
                        "description": "",
                        "diagnosis": "",
                        "remediations": "",
                        "variables": {},
                    },
                },
                "PreSubscription2": {
                    "messages": [
                        {
                            "level": 51,
                            "id": "WARNING_ID",
                            "title": "Warning",
                            "description": "Action warning",
                            "diagnosis": "User warning",
                            "remediations": "move on",
                            "variables": {},
                        }
                    ],
                    "result": {
                        "level": 101,
                        "id": "SKIPPED",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            {
                ("PreSubscription", "SUCCESS"): {
                    "level": 0,
                    "title": "",
                    "description": "",
                    "remediations": "",
                    "diagnosis": "",
                    "variables": {},
                },
                ("PreSubscription2", "SKIPPED"): {
                    "level": 101,
                    "title": "Skip",
                    "description": "Action skip",
                    "remediations": "move on",
                    "diagnosis": "User skip",
                    "variables": {},
                },
                ("PreSubscription2", "WARNING_ID"): {
                    "level": 51,
                    "title": "Warning",
                    "description": "Action warning",
                    "remediations": "move on",
                    "diagnosis": "User warning",
                    "variables": {},
                },
            },
        ),
    ),
)
def test_get_combined_results_and_message(results, expected):
    combined_results_and_message = report.get_combined_results_and_message(results)

    assert combined_results_and_message == expected


@pytest.mark.parametrize(
    ("actions", "expected"),
    (
        (
            {
                "action1": {
                    "result": {"level": STATUS_CODE["ERROR"]},
                    "messages": [{"level": STATUS_CODE["SUCCESS"]}],
                },
                "action2": {
                    "result": {"level": STATUS_CODE["WARNING"]},
                    "messages": [{"level": STATUS_CODE["SUCCESS"]}],
                },
            },
            "ERROR",
        ),
        (
            {
                "action1": {
                    "result": {"level": STATUS_CODE["SUCCESS"]},
                    "messages": [],
                },
                "action2": {
                    "result": {"level": STATUS_CODE["SUCCESS"]},
                    "messages": [],
                },
            },
            "SUCCESS",
        ),
        (
            {
                "action1": {
                    "result": {"level": STATUS_CODE["SUCCESS"]},
                    "messages": [{"level": STATUS_CODE["WARNING"]}],
                },
                "action2": {
                    "result": {"level": STATUS_CODE["SUCCESS"]},
                    "messages": [],
                },
            },
            "WARNING",
        ),
        (
            {
                "action1": {
                    "result": {"level": STATUS_CODE["INFO"]},
                    "messages": [{"level": STATUS_CODE["SUCCESS"]}],
                },
                "action2": {
                    "result": {"level": STATUS_CODE["SUCCESS"]},
                    "messages": [],
                },
            },
            "INFO",
        ),
        (
            {
                "action1": {
                    "result": {"level": STATUS_CODE["INFO"]},
                    "messages": [{"level": STATUS_CODE["SUCCESS"]}],
                },
                "action2": {
                    "result": {"level": STATUS_CODE["SKIP"]},
                    "messages": [],
                },
            },
            "SKIP",
        ),
        (
            {
                "action1": {
                    "result": {"level": STATUS_CODE["INFO"]},
                    "messages": [{"level": STATUS_CODE["OVERRIDABLE"]}],
                },
                "action2": {
                    "result": {"level": STATUS_CODE["ERROR"]},
                    "messages": [],
                },
            },
            "ERROR",
        ),
    ),
)
def test_find_highest_report_level_expected(actions, expected):
    """Should be sorted descending from the highest status to the lower one."""
    result = report.find_highest_report_level(actions)
    assert result == expected


def test_find_highest_report_level_unknown_status():
    """Should ignore unknown statuses in report"""
    expected_output = "ERROR"

    action_results_test = {
        "action1": {
            "result": {"level": STATUS_CODE["ERROR"]},
            "messages": [{"level": STATUS_CODE["SUCCESS"]}, {"level": STATUS_CODE["WARNING"]}],
        },
        "action2": {
            "result": {"level": STATUS_CODE["WARNING"]},
            "messages": [{"level": "FOO"}, {"level": STATUS_CODE["INFO"]}],
        },
    }
    result = report.find_highest_report_level(action_results_test)
    assert result == expected_output


def test_pre_conversion_report(monkeypatch, caplog):
    monkeypatch.setattr(report, "_summary", mock.Mock())
    report.pre_conversion_report({})
    assert "Pre-conversion analysis report" in caplog.records[-1].message


def test_post_conversion_report(monkeypatch, caplog):
    monkeypatch.setattr(report, "_summary", mock.Mock())
    report.post_conversion_report({})
    assert "Post-conversion report" in caplog.records[-1].message
