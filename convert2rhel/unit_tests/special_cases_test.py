import pytest
import six

from convert2rhel import special_cases
from convert2rhel.unit_tests import run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos8, oracle8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@mock.patch("convert2rhel.special_cases.remove_iwlax2xx_firmware")
def test_check_and_resolve(remove_iwlax2xx_firmware_mock, monkeypatch):
    special_cases.check_and_resolve()
    remove_iwlax2xx_firmware_mock.assert_called()


@pytest.mark.parametrize(
    (
        "is_iwl7260_installed",
        "is_iwlax2xx_installed",
        "subprocess_output",
        "subprocess_call_count",
        "expected_message",
    ),
    (
        (
            True,
            True,
            ("output", 0),
            1,
            "Removing the iwlax2xx-firmware package. Its content is provided by the RHEL iwl7260-firmware package.",
        ),
        (True, True, ("output", 1), 1, "Unable to remove the package iwlax2xx-firmware."),
        (
            True,
            False,
            ("output", 0),
            0,
            "The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.",
        ),
        (
            False,
            True,
            ("output", 0),
            0,
            "The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.",
        ),
        (
            False,
            False,
            ("output", 0),
            0,
            "The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.",
        ),
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
