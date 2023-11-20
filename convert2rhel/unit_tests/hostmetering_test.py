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

from convert2rhel import hostmetering, toolopts, utils
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import RunSubprocessMocked


def test_payg(monkeypatch):
    monkeypatch.setattr(system_info, "version", Version(7, 9))
    monkeypatch.setattr(system_info, "releasever", "")  # reset as other test set it
    monkeypatch.setattr(toolopts.tool_opts, "payg", True)
    run_mock = RunSubprocessMocked(return_value=("mock", 0))
    monkeypatch.setattr(hostmetering, "run_subprocess", run_mock)
    monkeypatch.setattr(utils, "run_subprocess", run_mock)

    ret = hostmetering.configure_host_metering()
    if not ret:
        pytest.fail("Failed to configure host-metering.")

    copr_repo = "copr:copr.fedorainfracloud.org:pvoborni:host-metering"
    run_mock.assert_any_call(
        ["yum", "install", "-y", "--enablerepo=%s" % copr_repo, "host-metering"], print_output=True
    )
    run_mock.assert_any_call(["systemctl", "enable", "host-metering.service"])
    run_mock.assert_any_call(["systemctl", "start", "host-metering.service"])


def test_no_payg(monkeypatch):
    monkeypatch.setattr(system_info, "version", Version(7, 9))
    monkeypatch.setattr(toolopts.tool_opts, "payg", False)
    run_mock = RunSubprocessMocked(return_value=("mock", 0))
    monkeypatch.setattr(hostmetering, "run_subprocess", run_mock)
    monkeypatch.setattr(utils, "run_subprocess", run_mock)

    ret = hostmetering.configure_host_metering()
    if ret:
        pytest.fail("Configured host-metering when it shouldn't.")

    utils.run_subprocess.assert_not_called()
