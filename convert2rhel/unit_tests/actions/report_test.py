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

from convert2rhel.actions import report


@pytest.mark.parametrize(
    ("dictionary", "look_for", "expected"), (({"zero": 0}, 0, "zero"), ({"zero": 0, "one": 1}, 0, "zero"))
)
def test_dictionary_value_lookup(dictionary, look_for, expected):
    assert report._dictionary_value_lookup(dictionary, look_for) == expected


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test that all messages are being used with the `include_all_reports`
        # parameter.
        (
            {"PreSubscription": {"status": 0, "error_id": None, "message": "All good!"}},
            True,
            ["(SUCCESS) PreSubscription: All good!"],
        ),
        (
            {"PreSubscription": {"status": 0, "error_id": None, "message": None}},
            True,
            ["(SUCCESS) PreSubscription: [No further information given]"],
        ),
        (
            {
                "PreSubscription": {"status": 0, "error_id": None, "message": "All good!"},
                "PreSubscription2": {"status": 300, "error_id": "SOME_WARNING", "message": "WARNING MESSAGE"},
            },
            True,
            ["(SUCCESS) PreSubscription: All good!", "(WARNING) PreSubscription2.SOME_WARNING: WARNING MESSAGE"],
        ),
        # Test that messages that are bellow WARNING (300) will not appear in
        # the logs.
        (
            {"PreSubscription": {"status": 0, "error_id": None, "message": None}},
            False,
            ["No problems detected during the analysis!"],
        ),
        (
            {
                "PreSubscription": {"status": 0, "error_id": None, "message": None},
                "PreSubscription2": {"status": 300, "error_id": "SOME_WARNING", "message": "WARNING MESSAGE"},
            },
            False,
            ["(WARNING) PreSubscription2.SOME_WARNING: WARNING MESSAGE"],
        ),
        # Test all messages are displayed, WARNING and higher
        (
            {
                "PreSubscription1": {"status": 300, "error_id": "SOME_WARNING", "message": "WARNING MESSAGE"},
                "PreSubscription2": {"status": 450, "error_id": "SKIPPED", "message": "SKIP MESSAGE"},
            },
            False,
            [
                "(SKIP) PreSubscription2.SKIPPED: SKIP MESSAGE",
                "(WARNING) PreSubscription1.SOME_WARNING: WARNING MESSAGE",
            ],
        ),
        (
            {
                "WarningAction": {"status": 300, "error_id": "WARNING", "message": "WARNING MESSAGE"},
                "SkipAction": {"status": 450, "error_id": "SKIP", "message": "SKIP MESSAGE"},
                "OverridableAction": {"status": 600, "error_id": "OVERRIDABLE", "message": "OVERRIDABLE MESSAGE"},
                "ErrorAction": {"status": 900, "error_id": "ERROR", "message": "ERROR MESSAGE"},
                "FatalAction": {"status": 1200, "error_id": "FATAL", "message": "FATAL MESSAGE"},
            },
            False,
            [
                "(FATAL) FatalAction.FATAL: FATAL MESSAGE",
                "(ERROR) ErrorAction.ERROR: ERROR MESSAGE",
                "(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE",
                "(SKIP) SkipAction.SKIP: SKIP MESSAGE",
                "(WARNING) WarningAction.WARNING: WARNING MESSAGE",
            ],
        ),
    ),
)
def test_summary(results, expected_results, include_all_reports, caplog):
    report.summary(results, include_all_reports)

    for expected in expected_results:
        assert any((expected in record.message) for record in caplog.records)


@pytest.mark.parametrize(
    ("results", "include_all_reports", "expected_results"),
    (
        # Test all messages are displayed, WARNING and higher
        (
            {
                "PreSubscription1": {"status": 300, "error_id": "SOME_WARNING", "message": "WARNING MESSAGE"},
                "PreSubscription2": {"status": 450, "error_id": "SKIPPED", "message": "SKIP MESSAGE"},
            },
            False,
            [
                (0, "(SKIP) PreSubscription2.SKIPPED: SKIP MESSAGE"),
                (1, "(WARNING) PreSubscription1.SOME_WARNING: WARNING MESSAGE"),
            ],
        ),
        (
            {
                "WarningAction": {"status": 300, "error_id": "WARNING", "message": "WARNING MESSAGE"},
                "SkipAction": {"status": 450, "error_id": "SKIP", "message": "SKIP MESSAGE"},
                "OverridableAction": {"status": 600, "error_id": "OVERRIDABLE", "message": "OVERRIDABLE MESSAGE"},
                "ErrorAction": {"status": 900, "error_id": "ERROR", "message": "ERROR MESSAGE"},
                "FatalAction": {"status": 1200, "error_id": "FATAL", "message": "FATAL MESSAGE"},
            },
            False,
            [
                (0, "(FATAL) FatalAction.FATAL: FATAL MESSAGE"),
                (1, "(ERROR) ErrorAction.ERROR: ERROR MESSAGE"),
                (2, "(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE"),
                (3, "(SKIP) SkipAction.SKIP: SKIP MESSAGE"),
                (4, "(WARNING) WarningAction.WARNING: WARNING MESSAGE"),
            ],
        ),
        # Message order with `include_all_reports` set to True.
        (
            {
                "PreSubscription": {"status": 0, "error_id": None, "message": "All good!"},
                "WarningAction": {"status": 300, "error_id": "WARNING", "message": "WARNING MESSAGE"},
                "SkipAction": {"status": 450, "error_id": "SKIP", "message": "SKIP MESSAGE"},
                "OverridableAction": {"status": 600, "error_id": "OVERRIDABLE", "message": "OVERRIDABLE MESSAGE"},
                "ErrorAction": {"status": 900, "error_id": "ERROR", "message": "ERROR MESSAGE"},
                "FatalAction": {"status": 1200, "error_id": "FATAL", "message": "FATAL MESSAGE"},
            },
            True,
            [
                (0, "(FATAL) FatalAction.FATAL: FATAL MESSAGE"),
                (1, "(ERROR) ErrorAction.ERROR: ERROR MESSAGE"),
                (2, "(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE"),
                (3, "(SKIP) SkipAction.SKIP: SKIP MESSAGE"),
                (4, "(WARNING) WarningAction.WARNING: WARNING MESSAGE"),
                (5, "(SUCCESS) PreSubscription: All good!"),
            ],
        ),
    ),
)
def test_summary_ordering(results, include_all_reports, expected_results, caplog):
    report.summary(results, include_all_reports)

    # Get the order and the message
    log_ordering = ((index, record.message) for index, record in enumerate(caplog.records))
    assert expected_results == list(log_ordering)
