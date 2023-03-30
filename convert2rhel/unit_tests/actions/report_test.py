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

from convert2rhel.actions import STATUS_CODE, report


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
            },
            False,
            [
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
                "PreSubscription1": {
                    "status": STATUS_CODE["WARNING"],
                    "error_id": "SOME_WARNING",
                    "message": "WARNING MESSAGE",
                },
                "PreSubscription2": {"status": STATUS_CODE["SKIP"], "error_id": "SKIPPED", "message": "SKIP MESSAGE"},
            },
            False,
            [
                (0, "(SKIP) PreSubscription2.SKIPPED: SKIP MESSAGE"),
                (1, "(WARNING) PreSubscription1.SOME_WARNING: WARNING MESSAGE"),
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
                (0, "(ERROR) ErrorAction.ERROR: ERROR MESSAGE"),
                (1, "(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE"),
                (2, "(SKIP) SkipAction.SKIP: SKIP MESSAGE"),
                (3, "(WARNING) WarningAction.WARNING: WARNING MESSAGE"),
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
                (0, "(ERROR) ErrorAction.ERROR: ERROR MESSAGE"),
                (1, "(OVERRIDABLE) OverridableAction.OVERRIDABLE: OVERRIDABLE MESSAGE"),
                (2, "(SKIP) SkipAction.SKIP: SKIP MESSAGE"),
                (3, "(WARNING) WarningAction.WARNING: WARNING MESSAGE"),
                (4, "(SUCCESS) PreSubscription: All good!"),
            ],
        ),
    ),
)
def test_summary_ordering(results, include_all_reports, expected_results, caplog):
    report.summary(results, include_all_reports)

    # Get the order and the message
    log_ordering = ((index, record.message) for index, record in enumerate(caplog.records))
    assert expected_results == list(log_ordering)
