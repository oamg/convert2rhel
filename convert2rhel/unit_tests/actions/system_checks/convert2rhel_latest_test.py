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

from convert2rhel import actions, exceptions, repo, systeminfo, unit_tests, utils
from convert2rhel.actions.system_checks import convert2rhel_latest


@pytest.fixture
def convert2rhel_latest_action_instance():
    return convert2rhel_latest.Convert2rhelLatest()


@pytest.fixture
def prepare_convert2rhel_latest_action(monkeypatch, tmpdir, request, global_system_info):
    """Mock the environment for testing the Convert2rhelLatest action.

    The "request" parameter is passed to the fixture by "indirect=True" of the pytest parametrize.

    :return: a tuple with the executed and the latest available convert2rhel versions
    """
    monkeypatch.setattr(convert2rhel_latest, "system_info", global_system_info)

    marker = request.param
    monkeypatch.setattr(
        convert2rhel_latest.Convert2rhelLatest,
        "_download_convert2rhel_repofile",
        mock.Mock(return_value="/test/path.py"),
    )
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
        ("prepare_convert2rhel_latest_action",),
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
    def test_convert2rhel_latest_outdated_version_inhibitor(
        self, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
    ):
        """When runnnig on a supported major version, we issue an error = inhibitor."""
        convert2rhel_latest_action_instance.run()

        running_version, latest_version = prepare_convert2rhel_latest_action

        unit_tests.assert_actions_result(
            convert2rhel_latest_action_instance,
            level="OVERRIDABLE",
            id="OUT_OF_DATE",
            title="Outdated convert2rhel version detected",
            description="An outdated convert2rhel version has been detected",
            diagnosis=(
                "You are currently running {} and the latest version of convert2rhel is {}.\n"
                "Only the latest version is supported for conversion.".format(running_version, latest_version)
            ),
            remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
        )

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
    def test_convert2rhel_latest_outdated_version_warning(
        self, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
    ):
        """When runnnig on an older unsupported major version, we issue just a warning instead of an inhibitor."""
        convert2rhel_latest_action_instance.run()

        running_version, latest_version = prepare_convert2rhel_latest_action

        expected = {
            actions.ActionMessage(
                level="WARNING",
                id="OUTDATED_CONVERT2RHEL_VERSION",
                title="Outdated convert2rhel version detected",
                description="An outdated convert2rhel version has been detected",
                diagnosis=(
                    "You are currently running {} and the latest version of convert2rhel is {}.\n"
                    "We encourage you to update to the latest version.".format(running_version, latest_version)
                ),
                remediations=None,
            )
        }
        assert expected.issuperset(convert2rhel_latest_action_instance.messages)
        assert expected.issubset(convert2rhel_latest_action_instance.messages)

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
        self, caplog, monkeypatch, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
    ):
        monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_ALLOW_OLDER_VERSION": "1"})
        convert2rhel_latest_action_instance.run()

        running_version, latest_version = prepare_convert2rhel_latest_action

        log_msg = (
            "You are currently running {} and the latest version of convert2rhel is {}.\n"
            "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion".format(
                running_version, latest_version
            )
        )
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
        (
            [
                {
                    "local_version": "0.17.0",
                    "package_version": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_repoquery": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_qf": "C2R convert2rhel-0:0.17.0-1.el7.noarch",
                    "package_version_V": 0,
                    "pmajor": "6",
                    "running_version": "0:0.17.1-1.el7",
                    "latest_version": "0:0.17.0-1.el7",
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
    def test_convert2rhel_latest_up_to_date_version(
        self, caplog, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
    ):
        convert2rhel_latest_action_instance.run()

        log_msg = "Latest available convert2rhel version is installed."
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
    def test_convert2rhel_latest_repoquery_error(
        self, caplog, monkeypatch, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
    ):
        monkeypatch.setattr(
            utils, "run_subprocess", unit_tests.RunSubprocessMocked(return_value=("Repoquery did not run", 1))
        )
        expected = {
            actions.ActionMessage(
                level="WARNING",
                id="CONVERT2RHEL_LATEST_CHECK_SKIP",
                title="convert2rhel latest version check skip",
                description="Did not perform the convert2hel latest version check",
                diagnosis=(
                    "Couldn't check if the current installed convert2rhel is the latest version.\n"
                    "repoquery failed with the following output:\nRepoquery did not run"
                ),
                remediations=None,
            )
        }
        convert2rhel_latest_action_instance.run()

        log_msg = (
            "Couldn't check if the current installed convert2rhel is the latest version.\n"
            "repoquery failed with the following output:\nRepoquery did not run"
        )
        assert log_msg in caplog.text
        assert expected.issuperset(convert2rhel_latest_action_instance.messages)
        assert expected.issubset(convert2rhel_latest_action_instance.messages)

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
    def ttest_convert2rhel_latest_multiple_packages(
        self, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
    ):
        convert2rhel_latest_action_instance.run()

        running_version, latest_version = prepare_convert2rhel_latest_action

        unit_tests.assert_actions_result(
            convert2rhel_latest_action_instance,
            level="OVERRIDABLE",
            id="OUT_OF_DATE",
            title="Outdated convert2rhel version detected",
            description="An outdated convert2rhel version has been detected",
            diagnosis=(
                "You are currently running {} and the latest version of convert2rhel is {}.\n"
                "Only the latest version is supported for conversion.".format(running_version, latest_version)
            ),
            remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
        )

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
        self, caplog, monkeypatch, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
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

        running_version, latest_version = prepare_convert2rhel_latest_action
        convert2rhel_latest_action_instance.run()

        log_msg = (
            "Some files in the convert2rhel package have changed so the installed convert2rhel is not what was packaged."
            " We will check that the version of convert2rhel ({}) is the latest but ignore the rpm release.".format(
                running_version
            )
        )

        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
        self, caplog, monkeypatch, convert2rhel_latest_action_instance, prepare_convert2rhel_latest_action
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

        running_version, latest_version = prepare_convert2rhel_latest_action
        convert2rhel_latest_action_instance.run()

        log_msg = "Couldn't determine the rpm release; We will check that the version of convert2rhel ({}) is the latest but ignore the rpm release.".format(
            running_version
        )

        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("prepare_convert2rhel_latest_action",),
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
    def test_convert2rhel_latest_bad_NEVRA_to_parse_pkg_string(
        self,
        convert2rhel_latest_action_instance,
        prepare_convert2rhel_latest_action,
    ):
        generator = extract_convert2rhel_versions_generator()

        # Use mock.patch with side_effect set to the generator
        mock.patch(
            "convert2rhel_latest._extract_convert2rhel_versions",
            side_effect=generator,
        )
        convert2rhel_latest_action_instance.run()

        running_version, latest_version = prepare_convert2rhel_latest_action

        unit_tests.assert_actions_result(
            convert2rhel_latest_action_instance,
            level="OVERRIDABLE",
            id="OUT_OF_DATE",
            title="Outdated convert2rhel version detected",
            description="An outdated convert2rhel version has been detected",
            diagnosis=(
                "You are currently running {} and the latest version of convert2rhel is {}.\n"
                "Only the latest version is supported for conversion.".format(running_version, latest_version)
            ),
            remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
        )

    def test_convert2rhel_latest_unable_to_get_c2r_repofile(
        self, global_system_info, monkeypatch, convert2rhel_latest_action_instance
    ):
        monkeypatch.setattr(convert2rhel_latest, "system_info", global_system_info)
        # Setting the major version to 0 will make _download_convert2rhel_repofile() generate
        # a WARNING-level report message and return None
        monkeypatch.setattr(global_system_info, "version", systeminfo.Version(0, 0))

        convert2rhel_latest_action_instance.run()

        assert (
            "skipped due to an unexpected system version" in convert2rhel_latest_action_instance.messages[0].description
        )
        assert convert2rhel_latest_action_instance.result.level == actions.STATUS_CODE["SUCCESS"]

    @pytest.mark.parametrize(
        ("major_version", "download_raises", "write_raises", "expected_return", "msg_diag"),
        (
            (8, False, False, "/test/path.py", None),
            (0, True, True, None, "Detected major version: 0"),
            (8, True, True, None, "download failed"),
            (8, True, False, None, "download failed"),
            (8, False, True, None, "store failed"),
        ),
    )
    def test_download_convert2rhel_repofile(
        self,
        monkeypatch,
        global_system_info,
        major_version,
        download_raises,
        write_raises,
        expected_return,
        msg_diag,
    ):
        monkeypatch.setattr(convert2rhel_latest, "system_info", global_system_info)
        monkeypatch.setattr(global_system_info, "version", systeminfo.Version(major_version, 0))
        if download_raises:
            monkeypatch.setattr(
                repo,
                "download_repofile",
                mock.Mock(side_effect=exceptions.CriticalError(id_="ID", title="Title", description="download failed")),
            )
        else:
            monkeypatch.setattr(repo, "download_repofile", mock.Mock(return_value="file content string"))
        if write_raises:
            monkeypatch.setattr(
                repo,
                "write_temporary_repofile",
                mock.Mock(side_effect=exceptions.CriticalError(id_="ID", title="Title", description="store failed")),
            )
        else:
            monkeypatch.setattr(repo, "write_temporary_repofile", mock.Mock(return_value="/test/path.py"))

        convert2rhel_latest_action_instance = convert2rhel_latest.Convert2rhelLatest()
        returned = convert2rhel_latest_action_instance._download_convert2rhel_repofile()

        assert returned == expected_return
        if msg_diag:
            assert msg_diag in convert2rhel_latest_action_instance.messages[0].diagnosis


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
