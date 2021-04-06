import sys

import pytest

from convert2rhel import special_cases
from convert2rhel.special_cases import (
    OPENJDK_RPM_STATE_DIR,
    check_and_resolve,
    perform_java_openjdk_workaround,
)


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


@pytest.mark.parametrize(
    (
        "has_openjdk",
        "can_successfully_apply_workaround",
        "mkdir_p_should_raise",
        "check_message_in_log",
        "check_message_not_in_log",
    ),
    [
        # All is fine case
        (
            True,
            True,
            None,
            "openjdk workaround applied successfully.",
            "Unable to create the %s" % OPENJDK_RPM_STATE_DIR,
        ),
        # openjdk presented, but OSError when trying to apply workaround
        (
            True,
            False,
            OSError,
            "Unable to create the %s" % OPENJDK_RPM_STATE_DIR,
            "openjdk workaround applied successfully.",
        ),
        # No openjdk
        (False, False, None, None, None),
    ],
)
def test_perform_java_openjdk_workaround(
    has_openjdk,
    can_successfully_apply_workaround,
    mkdir_p_should_raise,
    check_message_in_log,
    check_message_not_in_log,
    monkeypatch,
    caplog,
):
    mkdir_p_mocked = (
        mock.Mock(side_effect=mkdir_p_should_raise())
        if mkdir_p_should_raise
        else mock.Mock()
    )
    has_rpm_mocked = mock.Mock(return_value=has_openjdk)

    monkeypatch.setattr(
        special_cases,
        "mkdir_p",
        value=mkdir_p_mocked,
    )
    monkeypatch.setattr(
        special_cases.system_info,
        "is_rpm_installed",
        value=has_rpm_mocked,
    )
    perform_java_openjdk_workaround()

    # check logs
    if check_message_in_log:
        assert check_message_in_log in caplog.text
    if check_message_not_in_log:
        assert check_message_not_in_log not in caplog.text

    # check calls
    if has_openjdk:
        mkdir_p_mocked.assert_called()
    else:
        mkdir_p_mocked.assert_not_called()
    has_rpm_mocked.assert_called()


def test_check_and_resolve(monkeypatch):
    perform_java_openjdk_workaround_mock = mock.Mock()
    monkeypatch.setattr(
        special_cases,
        "perform_java_openjdk_workaround",
        value=perform_java_openjdk_workaround_mock,
    )
    check_and_resolve()
    perform_java_openjdk_workaround_mock.assert_called()
