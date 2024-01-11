# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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

import os

import pytest
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import actions, systeminfo, unit_tests, utils
from convert2rhel.actions.system_checks import convert2rhel_latest


@pytest.fixture
def convert2rhel_latest_action():
    return convert2rhel_latest.Convert2rhelLatest()


@pytest.fixture
def convert2rhel_latest_version_test(monkeypatch, tmpdir, request, global_system_info):
    monkeypatch.setattr(convert2rhel_latest, "system_info", global_system_info)
    global_system_info.has_internet_access = True

    marker = request.param
    monkeypatch.setattr(convert2rhel_latest, "running_convert2rhel_version", marker["local_version"])

    # Mocking run_subprocess for different command outputs
    command_outputs = [
        (marker["package_version_repoquery"], 0),  # Output for repoquery
        (marker["package_version_qf"], 0),  # Output for rpm -qf
        (marker["package_version_V"], 0),  # Output for rpm -V
    ]
    run_subprocess_mocked = mock.Mock(spec=utils.run_subprocess, side_effect=command_outputs)

    monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)
    monkeypatch.setattr(global_system_info, "version", systeminfo.Version(marker["pmajor"], 0))
    monkeypatch.setattr(utils, "TMP_DIR", str(tmpdir))

    return (
        marker["running_version"],
        marker["latest_version"],
    )


@pytest.fixture
def current_version(request):
    return request.param


class TestCheckConvert2rhelLatest:
    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.20",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.20-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "7",
                    "running_version": "0:0.20-1.el7",
                    "latest_version": "0:0.18-1.el7",
                }
            ],
            [
                {
                    "local_version": "0.20",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.20-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "7",
                    "running_version": "0.20",
                    "latest_version": "0.22.0",
                }
            ],
            [
                {
                    "local_version": "0.20.0",
                    "package_version": "C2R convert2rhel-0:0.22.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.20.0-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "7",
                    "running_version": "0:0.20.0",
                    "latest_version": "0:0.18-1.el7",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_offline(
        self, caplog, convert2rhel_latest_action, convert2rhel_latest_version_test, global_system_info
    ):
        global_system_info.has_internet_access = False
        convert2rhel_latest_action.run()
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="CONVERT2RHEL_LATEST_CHECK_SKIP_NO_INTERNET",
                    title="Skipping convert2rhel latest version check",
                    description="Skipping the check because no internet connection has been detected.",
                    diagnosis=None,
                    remediations=None,
                ),
            )
        )

        log_msg = "Skipping the check because no internet connection has been detected."
        assert log_msg in caplog.text
        assert convert2rhel_latest_action.result.level == actions.STATUS_CODE["SUCCESS"]
        assert expected.issuperset(convert2rhel_latest_action.messages)
        assert expected.issubset(convert2rhel_latest_action.messages)

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.21",
                    "package_version": "C2R convert2rhel-0:0.22-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.22-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.21-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "0.21",
                    "latest_version": "0.22",
                }
            ],
            [
                {
                    "local_version": "0.21",
                    "package_version": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.21-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "0.21",
                    "latest_version": "1.10",
                }
            ],
            [
                {
                    "local_version": "1.21.0",
                    "package_version": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.21.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "1.21.0",
                    "latest_version": "1.21.1",
                }
            ],
            [
                {
                    "local_version": "1.21",
                    "package_version": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.21-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "1.21",
                    "latest_version": "1.21.1",
                }
            ],
            [
                {
                    "local_version": "1.21.1",
                    "package_version": "C2R convert2rhel-0:1.22-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.22-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "1.21.1",
                    "latest_version": "1.22",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_action_error(self, convert2rhel_latest_action, convert2rhel_latest_version_test):
        convert2rhel_latest_action.run()

        running_version, latest_version = convert2rhel_latest_version_test

        unit_tests.assert_actions_result(
            convert2rhel_latest_action,
            level="ERROR",
            id="OUT_OF_DATE",
            title="Outdated convert2rhel version detected",
            description="An outdated convert2rhel version has been detected",
            diagnosis=(
                "You are currently running %s and the latest version of convert2rhel is %s.\n"
                "Only the latest version is supported for conversion." % (running_version, latest_version)
            ),
            remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
        )

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.21",
                    "package_version": "C2R convert2rhel-0:0.22-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.22-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.21-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "6",
                    "running_version": "0.21",
                    "latest_version": "0.22",
                }
            ],
            [
                {
                    "local_version": "0.21",
                    "package_version": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.21-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "6",
                    "running_version": "0.21",
                    "latest_version": "1.10",
                }
            ],
            [
                {
                    "local_version": "1.21.0",
                    "package_version": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.21.0-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "6",
                    "running_version": "1.21.0",
                    "latest_version": "1.21.1",
                }
            ],
            [
                {
                    "local_version": "1.21",
                    "package_version": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.21-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "6",
                    "running_version": "1.21",
                    "latest_version": "1.21.1",
                }
            ],
            [
                {
                    "local_version": "1.21.1",
                    "package_version": "C2R convert2rhel-0:0.22-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.22-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.21.1-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "6",
                    "running_version": "1.21.1",
                    "latest_version": "1.22",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_action_outdated_version(
        self, convert2rhel_latest_action, convert2rhel_latest_version_test
    ):
        convert2rhel_latest_action.run()

        running_version, latest_version = convert2rhel_latest_version_test

        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="OUTDATED_CONVERT2RHEL_VERSION",
                    title="Outdated convert2rhel version detected",
                    description="An outdated convert2rhel version has been detected",
                    diagnosis=(
                        "You are currently running %s and the latest version of convert2rhel is %s.\n"
                        "We encourage you to update to the latest version." % (running_version, latest_version)
                    ),
                    remediations=None,
                ),
            )
        )
        assert expected.issuperset(convert2rhel_latest_action.messages)
        assert expected.issubset(convert2rhel_latest_action.messages)

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.18.0",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "6",
                    "enset": "1",
                    "running_version": "0.18.0",
                    "latest_version": "0.22.0",
                }
            ],
            [
                {
                    "local_version": "0.18.1",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.18.1-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "enset": "1",
                    "running_version": "0.18.1",
                    "latest_version": "0.22.0",
                }
            ],
            [
                {
                    "local_version": "0.18.3",
                    "package_version": "C2R convert2rhel-0:0.22.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.22.1-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.18.3-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "enset": "1",
                    "running_version": "0.18.3",
                    "latest_version": "0.22.1",
                }
            ],
            [
                {
                    "local_version": "0.18",
                    "package_version": "C2R convert2rhel-0:1.10.2-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.10.2-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.18-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "enset": "1",
                    "running_version": "0.18",
                    "latest_version": "1.10.2",
                }
            ],
            [
                {
                    "local_version": "0.18.0",
                    "package_version": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "enset": "1",
                    "running_version": "0.18.0",
                    "latest_version": "1.10",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_log_check_env(
        self, caplog, monkeypatch, convert2rhel_latest_action, convert2rhel_latest_version_test
    ):
        monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_ALLOW_OLDER_VERSION": "1"})
        convert2rhel_latest_action.run()

        running_version, latest_version = convert2rhel_latest_version_test

        log_msg = (
            "You are currently running %s and the latest version of convert2rhel is %s.\n"
            "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion"
            % (running_version, latest_version)
        )
        assert log_msg in caplog.text

        deprecated_var_name = "CONVERT2RHEL_UNSUPPORTED_VERSION"
        assert deprecated_var_name not in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.17.0",
                    "package_version": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "6",
                    "running_version": "0.17.1",
                    "latest_version": "0.17.0",
                }
            ],
            [
                {
                    "local_version": "0.17.0",
                    "package_version": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "0.17.0",
                    "latest_version": "0.17.1",
                }
            ],
            [
                {
                    "local_version": "0.17.0",
                    "package_version": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.17.0",
                    "latest_version": "0.17.0",
                }
            ],
            [
                {
                    "local_version": "0.25.0",
                    "package_version": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.25.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "6",
                    "running_version": "0.25.0",
                    "latest_version": "0.17.0",
                }
            ],
            [
                {
                    "local_version": "0.25.0",
                    "package_version": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.25.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "0.25.0",
                    "latest_version": "0.17.0",
                }
            ],
            [
                {
                    "local_version": "0.25.0",
                    "package_version": "C2R convert2rhel-:0.18.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.25.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.25.0",
                    "latest_version": "0.18.0",
                }
            ],
            [
                {
                    "local_version": "1.10.0",
                    "package_version": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.10.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "1.10.0",
                    "latest_version": "0.18.0",
                }
            ],
            [
                {
                    "local_version": "1.10.1",
                    "package_version": "C2R convert2rhel-0:1.10.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:1.10.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.10.1-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "1.10.1",
                    "latest_version": "1.10.0",
                }
            ],
        ),
        indirect=True,
    )
    def test_c2r_up_to_date(self, caplog, monkeypatch, convert2rhel_latest_action, convert2rhel_latest_version_test):
        convert2rhel_latest_action.run()

        log_msg = "Latest available convert2rhel version is installed."
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "1.10.0",
                    "package_version": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.10.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "1.10.0",
                    "latest_version": "0.18.0",
                }
            ],
            [
                {
                    "local_version": "1.10",
                    "package_version": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.10-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "1.10",
                    "latest_version": "0.18.0",
                }
            ],
            [
                {
                    "local_version": "1.10.0",
                    "package_version": "C2R convert2rhel-:0.18-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:1.10.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "1.10.0",
                    "latest_version": "0.18",
                }
            ],
        ),
        indirect=True,
    )
    def test_c2r_up_to_date_repoquery_error(
        self, caplog, monkeypatch, convert2rhel_latest_action, convert2rhel_latest_version_test
    ):
        monkeypatch.setattr(
            utils, "run_subprocess", unit_tests.RunSubprocessMocked(return_value=("Repoquery did not run", 1))
        )
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="CONVERT2RHEL_LATEST_CHECK_SKIP",
                    title="convert2rhel latest version check skip",
                    description="Skipping the convert2hel latest version check",
                    diagnosis=(
                        "Couldn't check if the current installed convert2rhel is the latest version.\n"
                        "repoquery failed with the following output:\nRepoquery did not run"
                    ),
                    remediations=None,
                ),
            )
        )
        convert2rhel_latest_action.run()

        log_msg = (
            "Couldn't check if the current installed convert2rhel is the latest version.\n"
            "repoquery failed with the following output:\nRepoquery did not run"
        )
        assert log_msg in caplog.text
        assert expected.issuperset(convert2rhel_latest_action.messages)
        assert expected.issubset(convert2rhel_latest_action.messages)

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.19.0",
                    "package_version": "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.19.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.19.0",
                    "latest_version": "0.20.0",
                }
            ],
            [
                {
                    "local_version": "0.19",
                    "package_version": "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.19-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.19",
                    "latest_version": "0.20.0",
                }
            ],
            [
                {
                    "local_version": "0.19.0",
                    "package_version": "C2R convert2rhel-0:0.18-1.el7.noarch\nC2R convert2rhel-0:0.17-1.el7.noarch\nC2R convert2rhel-0:0.20-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.19.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.19.0",
                    "latest_version": "0.20",
                }
            ],
        ),
        indirect=True,
    )
    def test_c2r_up_to_date_multiple_packages(self, convert2rhel_latest_action, convert2rhel_latest_version_test):
        convert2rhel_latest_action.run()

        running_version, latest_version = convert2rhel_latest_version_test

        unit_tests.assert_actions_result(
            convert2rhel_latest_action,
            level="ERROR",
            id="OUT_OF_DATE",
            title="Outdated convert2rhel version detected",
            description="An outdated convert2rhel version has been detected",
            diagnosis=(
                "You are currently running %s and the latest version of convert2rhel is %s.\n"
                "Only the latest version is supported for conversion." % (running_version, latest_version)
            ),
            remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
        )

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.17.0",
                    "package_version": "C2R convert2rhel-0.18.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.17.0",
                    "latest_version": "0.18.0",
                }
            ],
            [
                {
                    "local_version": "0.17",
                    "package_version": "C2R convert2rhel-0.18.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.17",
                    "latest_version": "0.18.0",
                }
            ],
            [
                {
                    "local_version": "0.17.0",
                    "package_version": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.17.0",
                    "latest_version": "0.18",
                }
            ],
        ),
        indirect=True,
    )
    def test_c2r_up_to_date_deprecated_env_var(
        self, caplog, monkeypatch, convert2rhel_latest_action, convert2rhel_latest_version_test
    ):
        running_version, latest_version = convert2rhel_latest_version_test
        env = {"CONVERT2RHEL_UNSUPPORTED_VERSION": 1}
        monkeypatch.setattr(os, "environ", env)
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="DEPRECATED_ENVIRONMENT_VARIABLE",
                    title="Deprecated environment variable",
                    description="A deprecated environment variable has been detected",
                    diagnosis="You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_VERSION'",
                    remediations="Please switch to the 'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable instead",
                ),
                actions.ActionMessage(
                    level="WARNING",
                    id="ALLOW_OLDER_VERSION_ENVIRONMENT_VARIABLE",
                    title="Outdated convert2rhel version detected",
                    description="An outdated convert2rhel version has been detected",
                    diagnosis="You are currently running %s and the latest version of convert2rhel is %s.\n"
                    "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion"
                    % (running_version, latest_version),
                    remediations=None,
                ),
            )
        )
        convert2rhel_latest_action.run()

        log_msg = (
            "You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_VERSION'"
            " environment variable.  Please switch to 'CONVERT2RHEL_ALLOW_OLDER_VERSION'"
            " instead."
        )
        print(expected)
        print(convert2rhel_latest_action.messages)
        assert expected.issuperset(convert2rhel_latest_action.messages)
        assert expected.issubset(convert2rhel_latest_action.messages)
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.18.0",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_V": 1,
                    "pmajor": "6",
                    "running_version": "0.18.0",
                    "latest_version": "0.18.1",
                }
            ],
            [
                {
                    "local_version": "0.18.1",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_V": 1,
                    "pmajor": "7",
                    "running_version": "0.18.1",
                    "latest_version": "0.18.1",
                }
            ],
            [
                {
                    "local_version": "0.18.3",
                    "package_version": "C2R convert2rhel-0:0.22.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_V": 1,
                    "pmajor": "8",
                    "running_version": "0.18.3",
                    "latest_version": "0.18.1",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_rpm_V_check(
        self, caplog, monkeypatch, convert2rhel_latest_action, convert2rhel_latest_version_test
    ):
        def mock_run_subprocess(cmd, print_output=False):
            if "--qf" in cmd:
                return ("C2R convert2rhel-0:0.18.0-1.el7.noarch", 0)
            elif "-V" in cmd:
                return ("", 1)
            return ("", 0)

        monkeypatch.setattr(
            utils,
            "run_subprocess",
            mock_run_subprocess,
        )

        running_version, latest_version = convert2rhel_latest_version_test
        convert2rhel_latest_action.run()

        log_msg = (
            "Some files in the convert2rhel package have changed so the installed convert2rhel is not what was packaged."
            " We will check that the version of convert2rhel (%s) is the latest but ignore the rpm release."
            % running_version
        )

        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.18.0",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_V": " ",
                    "pmajor": "6",
                    "running_version": "0.18.0",
                    "latest_version": "0.18.1",
                }
            ],
            [
                {
                    "local_version": "0.18.1",
                    "package_version": "C2R convert2rhel-0:0.22.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "7",
                    "running_version": "0.18.1",
                    "latest_version": "0.18.1",
                }
            ],
            [
                {
                    "local_version": "0.18.3",
                    "package_version": "C2R convert2rhel-0:0.22.1-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0.18-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.18.3",
                    "latest_version": "0.18.1",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_rpm_qf_check(
        self, caplog, monkeypatch, convert2rhel_latest_action, convert2rhel_latest_version_test
    ):
        def mock_run_subprocess(cmd, print_output=False):
            if "repoquery" in cmd:
                return ("C2R convert2rhel-0:0.18.0-1.el7.noarch", 0)
            elif "--qf" in cmd:
                return ("", 1)
            return ("", 0)

        monkeypatch.setattr(
            utils,
            "run_subprocess",
            mock_run_subprocess,
        )

        running_version, latest_version = convert2rhel_latest_version_test
        convert2rhel_latest_action.run()

        log_msg = (
            "Couldn't determine the rpm release; We will check that the version of convert2rhel (%s) is the latest but ignore the rpm release."
            % running_version
        )

        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.19.0",
                    "package_version_repoquery": "C2R convert2rhel-0:0.18.0-1.el7.noarch\nNot a NEVRA that we was not filtered due to a bug\nC2R convert2rhel-0:0.20.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.19.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "8",
                    "running_version": "0.19.0",
                    "latest_version": "0.20.0",
                }
            ],
        ),
        indirect=True,
    )
    def test_bad_NEVRA_to_parse_pkg_string(
        self,
        convert2rhel_latest_action,
        convert2rhel_latest_version_test,
        monkeypatch,
    ):
        generator = extract_convert2rhel_versions_generator()

        # Use mock.patch with side_effect set to the generator
        mock.patch(
            "convert2rhel_latest._extract_convert2rhel_versions",
            side_effect=generator,
        )

        convert2rhel_latest_action.run()

        running_version, latest_version = convert2rhel_latest_version_test

        unit_tests.assert_actions_result(
            convert2rhel_latest_action,
            level="ERROR",
            id="OUT_OF_DATE",
            title="Outdated convert2rhel version detected",
            description="An outdated convert2rhel version has been detected",
            diagnosis=(
                "You are currently running %s and the latest version of convert2rhel is %s.\n"
                "Only the latest version is supported for conversion." % (running_version, latest_version)
            ),
            remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
        )


def extract_convert2rhel_versions_generator():
    # Yield bad output
    yield [
        "convert2rhel-0:0.18.0-1.el7.noarch",
        "Not a NEVRA that we was not filtered due to a bug",
        "convert2rhel-0:0.20.0-1.el7.noarch",
    ]

    # Yield good output
    yield [
        "convert2rhel-0:0.18.0-1.el7.noarch",
        "convert2rhel-0:0.19.0-1.el7.noarch",
        "convert2rhel-0:0.20.0-1.el7.noarch",
    ]


class Test_ExtractConvert2rhelVersions:
    @pytest.mark.parametrize(
        ("raw_versions", "expected_versions"),
        (
            (
                "C2R convert2rhel-0:0.18.0-1.el7.noarch\n",
                [
                    "convert2rhel-0:0.18.0-1.el7.noarch",
                ],
            ),
            (
                "C2R convert2rhel-1:1.0-99.el8.noarch\n",
                [
                    "convert2rhel-1:1.0-99.el8.noarch",
                ],
            ),
            (
                "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch",
                [
                    "convert2rhel-0:0.18.0-1.el7.noarch",
                    "convert2rhel-0:0.17.0-1.el7.noarch",
                    "convert2rhel-0:0.20.0-1.el7.noarch",
                ],
            ),
            (
                "C2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch\nconvert2rhel-0:0.21-1.el7.noarch",
                [
                    "convert2rhel-0:0.18.0-1.el7.noarch",
                    "convert2rhel-0:0.17.0-1.el7.noarch",
                    "convert2rhel-0:0.20.0-1.el7.noarch",
                ],
            ),
            (
                "C2R convert2rhel-0:0.18.0-1.el7.noarch\nconvert2rhel-0:0.21-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch\n",
                [
                    "convert2rhel-0:0.18.0-1.el7.noarch",
                    "convert2rhel-0:0.17.0-1.el7.noarch",
                    "convert2rhel-0:0.20.0-1.el7.noarch",
                ],
            ),
            (
                "convert2rhel-0:0.21-1.el7.noarch\nC2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch\n",
                [
                    "convert2rhel-0:0.18.0-1.el7.noarch",
                    "convert2rhel-0:0.17.0-1.el7.noarch",
                    "convert2rhel-0:0.20.0-1.el7.noarch",
                ],
            ),
            (
                "convert2rhel-0:0.21-1.el7.noarch\nC2R convert2rhel-0:0.18.0-1.el7.noarch\nC2R convert2rhel-0:0.17.0-1.el7.noarch\nconvert2rhel-1:2.27-9.el8.noarch\nC2R convert2rhel-0:0.20.0-1.el7.noarch\n",
                [
                    "convert2rhel-0:0.18.0-1.el7.noarch",
                    "convert2rhel-0:0.17.0-1.el7.noarch",
                    "convert2rhel-0:0.20.0-1.el7.noarch",
                ],
            ),
            (
                "",
                [],
            ),
            (
                "Output\nfrom repoquery where\nno strings were for\npackages",
                [],
            ),
        ),
    )
    def test_extract_convert2rhel_version(self, raw_versions, expected_versions):
        list_of_versions = convert2rhel_latest._extract_convert2rhel_versions(raw_versions)

        assert list_of_versions == expected_versions
