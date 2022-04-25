import sys

from collections import namedtuple

import pytest

from convert2rhel import special_cases
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos8, oracle8


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


@pytest.mark.parametrize(
    (
        "is_iwl7260_installed",
        "is_iwlax2xx_installed",
        "subprocess_output",
        "subprocess_call_count",
        "expected_message",
    ),
    (
        (True, True, ("output", 0), 1, "Removing iwlax2xx-firmware package."),
        (True, True, ("output", 1), 1, "Unable to remove the package iwlax2xx-firmware."),
        (True, False, ("output", 0), 0, "Removing iwlax2xx-firmware package."),
        (False, True, ("output", 0), 0, "Removing iwlax2xx-firmware package."),
        (False, False, ("output", 0), 0, "Removing iwlax2xx-firmware package."),
    ),
)
@oracle8
def test_remove_iwlax2xx_firmware(
    pretend_os,
    is_iwl7260_installed,
    is_iwlax2xx_installed,
    subprocess_output,
    subprocess_call_count,
    expected_message,
    monkeypatch,
    caplog,
):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("rpm", "-e", "--nodeps", "iwlax2xx-firmware"), subprocess_output),
        )
    )
    is_rpm_installed_mock = mock.Mock(side_effect=[is_iwl7260_installed, is_iwlax2xx_installed])
    monkeypatch.setattr(
        special_cases,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(special_cases.system_info, "is_rpm_installed", value=is_rpm_installed_mock)

    special_cases.remove_iwlax2xx_firmware()

    assert run_subprocess_mock.call_count == subprocess_call_count
    assert is_rpm_installed_mock.call_count == 2
    assert expected_message in caplog.records[-1].message


@centos8
def test_remove_iwlax2xx_firmware_not_ol8(pretend_os, caplog):
    special_cases.remove_iwlax2xx_firmware()

    assert "Relevant to Oracle Linux 8 only. Skipping." in caplog.records[-1].message
