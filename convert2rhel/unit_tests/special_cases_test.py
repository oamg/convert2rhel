import sys

from collections import namedtuple

import pytest

from convert2rhel import special_cases
from convert2rhel.systeminfo import system_info


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


@mock.patch("convert2rhel.special_cases.perform_java_openjdk_workaround")
@mock.patch("convert2rhel.special_cases.unprotect_shim_x64")
def test_check_and_resolve(unprotect_shim_x64, perform_java_openjdk_workaround_mock, monkeypatch):
    special_cases.check_and_resolve()

    perform_java_openjdk_workaround_mock.assert_called()
    unprotect_shim_x64.assert_called()


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
            "Unable to create the %s" % special_cases.OPENJDK_RPM_STATE_DIR,
        ),
        # openjdk presented, but OSError when trying to apply workaround
        (
            True,
            False,
            OSError,
            "Unable to create the %s" % special_cases.OPENJDK_RPM_STATE_DIR,
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
    mkdir_p_mocked = mock.Mock(side_effect=mkdir_p_should_raise()) if mkdir_p_should_raise else mock.Mock()
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
    special_cases.perform_java_openjdk_workaround()

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


@pytest.mark.parametrize(
    ("sys_id", "is_efi", "removal_ok", "log_msg"),
    (
        ("oracle", False, True, "Relevant to UEFI firmware only"),
        ("oracle", True, True, "removed in accordance with"),
        ("oracle", True, False, "Unable to remove"),
        ("centos", True, True, "Relevant to Oracle Linux 7 only"),
    ),
)
@mock.patch("os.remove")
@mock.patch("convert2rhel.special_cases.is_efi")
def test_unprotect_shim_x64(mock_is_efi, mock_os_remove, sys_id, is_efi, removal_ok, log_msg, monkeypatch, caplog):
    monkeypatch.setattr(system_info, "id", sys_id)
    mock_is_efi.return_value = is_efi
    monkeypatch.setattr(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    if not removal_ok:
        mock_os_remove.side_effect = OSError()

    special_cases.unprotect_shim_x64()

    assert log_msg in caplog.records[-1].message
    if sys_id == "oracle" and is_efi and removal_ok:
        mock_os_remove.assert_called_once()
