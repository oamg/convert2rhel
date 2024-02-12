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

import pytest
import six

from convert2rhel import hostmetering, systeminfo
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import RunSubprocessMocked, run_subprocess_side_effect


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    ("rhsm_facts", "os_version", "should_configure_metering", "envvar"),
    (
        (
            {},
            Version(7, 9),
            False,  # not on hyperscaler
            "auto",
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            True,
            "auto",
        ),
        (
            {"azure_instance_id": "012345678-abcde-efgh-1234-abcdefgh1234"},
            Version(7, 9),
            True,
            "auto",
        ),
        (
            {"gcp_instance_id": "12345-6789-abcd-efgh-0123456789ab"},
            Version(7, 9),
            True,
            "auto",
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(8, 8),
            False,  # not on RHEL 7
            "auto",
        ),
        (
            {"azure_instance_id": "012345678-abcde-efgh-1234-abcdefgh1234"},
            Version(8, 8),
            False,  # not on RHEL 7
            "auto",
        ),
        (
            {"gcp_instance_id": "12345-6789-abcd-efgh-0123456789ab"},
            Version(8, 8),
            False,  # not on RHEL 7
            "auto",
        ),
        (
            {},
            Version(7, 9),
            True,  # forced
            "force",
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(8, 8),
            True,  # forced
            "force",
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            False,
            "arbitrary",  # unknown option
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            False,
            "",  # option left empty
        ),
    ),
)
def test_configure_host_metering(monkeypatch, rhsm_facts, os_version, should_configure_metering, envvar):
    if envvar:
        monkeypatch.setenv("CONVERT2RHEL_CONFIGURE_HOST_METERING", envvar)

    monkeypatch.setattr(system_info, "version", os_version)
    monkeypatch.setattr(hostmetering, "get_rhsm_facts", mock.Mock(return_value=rhsm_facts))
    yum_mock = mock.Mock(return_value=(0, ""))
    monkeypatch.setattr(hostmetering, "call_yum_cmd", yum_mock)
    subprocess_mock = RunSubprocessMocked(return_string="mock")
    monkeypatch.setattr(hostmetering, "run_subprocess", subprocess_mock)
    monkeypatch.setattr(
        hostmetering.systeminfo,
        "is_systemd_managed_service_running",
        lambda name: True,
    )

    ret = hostmetering.configure_host_metering()

    if should_configure_metering:
        assert ret is True, "Should configure host-metering."
        yum_mock.assert_called_once_with("install", ["host-metering"])
        subprocess_mock.assert_any_call(["systemctl", "enable", "host-metering.service"])
        subprocess_mock.assert_any_call(["systemctl", "start", "host-metering.service"])
    else:
        assert ret is False, "Should not configure host-metering."
        assert yum_mock.call_count == 0, "Should not install anything."
        assert subprocess_mock.call_count == 0, "Should not configure anything."


@pytest.mark.parametrize(
    ("rhsm_facts", "expected"),
    (
        ({"aws_instance_id": "23143", "azure_instance_id": "12134", "gcp_instance_id": "34213"}, True),
        ({"aws_instance_id": "23143"}, True),
        ({"azure_instance_id": "12134"}, True),
        ({"gcp_instance_id": "34213"}, True),
        ({"invalid_instance_id": "00001"}, False),
    ),
)
def test_is_running_on_hyperscaler(rhsm_facts, expected):
    running_on_hyperscaler = hostmetering.is_running_on_hyperscaler(rhsm_facts)
    assert running_on_hyperscaler == expected


@pytest.mark.parametrize(
    ("enable_output", "enable_ret_code", "start_output", "start_ret_code", "managed_service", "expected"),
    (
        ("", 0, "", 0, True, True),
        ("", 0, "", 0, False, False),
        ("", 1, "", 0, True, False),
        ("", 0, "", 1, True, False),
        ("", 1, "", 1, True, False),
    ),
)
def test_enable_host_metering_service(
    enable_output, enable_ret_code, start_output, start_ret_code, managed_service, expected, monkeypatch
):
    systemctl_enable = ("systemctl", "enable", "host-metering.service")
    systemctl_start = ("systemctl", "start", "host-metering.service")

    # Mock rpm command
    run_subprocess_mock = RunSubprocessMocked(
        side_effect=run_subprocess_side_effect(
            (
                systemctl_enable,
                (
                    enable_output,
                    enable_ret_code,
                ),
            ),
            (systemctl_start, (start_output, start_ret_code)),
        ),
    )
    monkeypatch.setattr(hostmetering, "run_subprocess", value=run_subprocess_mock)
    monkeypatch.setattr(systeminfo, "is_systemd_managed_service_running", mock.Mock(return_value=managed_service))

    enable = hostmetering._enable_host_metering_service()
    assert enable == expected
