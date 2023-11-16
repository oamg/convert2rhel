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

from convert2rhel import hostmetering, utils
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import RunSubprocessMocked


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    ("rhsm_facts", "os_version", "should_configure_metering", "envvar"),
    (
        (
            {},
            Version(7, 9),
            False,  # not on hyperscaller
            None,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            True,
            None,
        ),
        (
            {"azure_instance_id": "012345678-abcde-efgh-1234-abcdefgh1234"},
            Version(7, 9),
            True,
            None,
        ),
        (
            {"gcp_instance_id": "12345-6789-abcd-efgh-0123456789ab"},
            Version(7, 9),
            True,
            None,
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(8, 8),
            False,  # not on RHEL 7
            None,
        ),
        (
            {"azure_instance_id": "012345678-abcde-efgh-1234-abcdefgh1234"},
            Version(8, 8),
            False,  # not on RHEL 7
            None,
        ),
        (
            {"gcp_instance_id": "12345-6789-abcd-efgh-0123456789ab"},
            Version(8, 8),
            False,  # not on RHEL 7
            None,
        ),
        # env var set behavior
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
            "no",  # disabled
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            True,
            "arbitrary",  # condition met
        ),
        (
            {"aws_instance_id": "i-1234567890abcdef0"},
            Version(7, 9),
            True,
            "",  # condition met
        ),
    ),
)
def test_hostmetering(monkeypatch, rhsm_facts, os_version, should_configure_metering, envvar):
    if envvar is not None:
        monkeypatch.setenv("CONVERT2RHEL_CONFIGURE_HOST_METERING", envvar)

    monkeypatch.setattr(system_info, "version", os_version)
    monkeypatch.setattr(system_info, "releasever", "")  # reset as other test set it
    monkeypatch.setattr(hostmetering, "get_rhsm_facts", mock.Mock(return_value=rhsm_facts))
    yum_mock = mock.Mock(return_value=(0, ""))
    monkeypatch.setattr(hostmetering, "call_yum_cmd", yum_mock)
    subprocess_mock = RunSubprocessMocked(return_string="mock")
    monkeypatch.setattr(hostmetering, "run_subprocess", subprocess_mock)

    ret = hostmetering.configure_host_metering()

    if should_configure_metering:
        assert ret is True, "Should configure host-metering."
        yum_mock.assert_called_once_with("install", ["host-metering"])
        subprocess_mock.assert_any_call(["systemctl", "enable", "host-metering.service"])
        subprocess_mock.assert_any_call(["systemctl", "start", "host-metering.service"])
    else:
        assert ret is False, "Should not configure host-metering."
        assert yum_mock.call_count == 0, "Should not install anythibg."
        assert subprocess_mock.call_count == 0, "Should not configure anything."
