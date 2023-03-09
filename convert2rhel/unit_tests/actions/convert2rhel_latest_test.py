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

from convert2rhel import systeminfo, utils
from convert2rhel.actions import convert2rhel_latest


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def convert2rhel_latest_check():
    return convert2rhel_latest.Convert2rhelLatest()


@pytest.fixture
def convert2rhel_latest_version_test(monkeypatch, tmpdir, request, global_system_info):
    monkeypatch.setattr(convert2rhel_latest, "system_info", global_system_info)
    global_system_info.has_internet_access = True

    marker = request.param
    monkeypatch.setattr(convert2rhel_latest, "installed_convert2rhel_version", marker["local_version"])

    run_subprocess_mocked = mock.Mock(spec=utils.run_subprocess, return_value=(marker["package_version"], 0))

    monkeypatch.setattr(utils, "run_subprocess", run_subprocess_mocked)
    monkeypatch.setattr(global_system_info, "version", systeminfo.Version(marker["pmajor"], 0))
    monkeypatch.setattr(utils, "TMP_DIR", str(tmpdir))

    return marker["local_version"], marker["package_version"]


class TestCheckConvert2rhelLatest:
    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        ([{"local_version": "0.20", "package_version": "convert2rhel-0:0.22-1.el7.noarch", "pmajor": "7"}],),
        indirect=True,
    )
    def test_convert2rhel_latest_offline(
        self, caplog, convert2rhel_latest_check, convert2rhel_latest_version_test, global_system_info
    ):
        global_system_info.has_internet_access = False
        convert2rhel_latest_check.run()

        log_msg = "Skipping the check because no internet connection has been detected."
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [{"local_version": "0.21", "package_version": "convert2rhel-0:0.22-1.el7.noarch", "pmajor": "7"}],
            [{"local_version": "0.21", "package_version": "convert2rhel-0:1.10-1.el7.noarch", "pmajor": "7"}],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_check_error(self, convert2rhel_latest_check, convert2rhel_latest_version_test):

        with pytest.raises(convert2rhel_latest.Convert2rhelLatestError) as exc_info:
            convert2rhel_latest_check.run()

        assert exc_info.value.code == "OUT_OF_DATE"

        local_version, package_version = convert2rhel_latest_version_test
        package_version = package_version[15:19]

        msg = (
            "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
            "Only the latest version is supported for conversion. If you want to ignore"
            " this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue."
            % (local_version, package_version)
        )
        assert exc_info.value.message == msg

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.18",
                    "package_version": "convert2rhel-0:0.22-1.el7.noarch",
                    "pmajor": "6",
                    "enset": "1",
                }
            ],
            [
                {
                    "local_version": "0.18",
                    "package_version": "convert2rhel-0:0.22-1.el7.noarch",
                    "pmajor": "7",
                    "enset": "1",
                }
            ],
            [
                {
                    "local_version": "0.18",
                    "package_version": "convert2rhel-0:0.22-1.el7.noarch",
                    "pmajor": "8",
                    "enset": "1",
                }
            ],
            [
                {
                    "local_version": "0.18",
                    "package_version": "convert2rhel-0:1.10-1.el7.noarch",
                    "pmajor": "8",
                    "enset": "1",
                }
            ],
        ),
        indirect=True,
    )
    def test_convert2rhel_latest_log_check_env(
        self, caplog, monkeypatch, convert2rhel_latest_check, convert2rhel_latest_version_test
    ):
        monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_ALLOW_OLDER_VERSION": "1"})
        convert2rhel_latest_check.run()

        local_version, package_version = convert2rhel_latest_version_test
        package_version = package_version[15:19]
        log_msg = (
            "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
            "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion"
            % (local_version, package_version)
        )
        assert log_msg in caplog.text

        deprecated_var_name = "CONVERT2RHEL_UNSUPPORTED_VERSION"
        assert deprecated_var_name not in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [{"local_version": "0.17", "package_version": "convert2rhel-0:0.17-1.el7.noarch", "pmajor": "6"}],
            [{"local_version": "0.17", "package_version": "convert2rhel-0:0.17-1.el7.noarch", "pmajor": "7"}],
            [{"local_version": "0.17", "package_version": "convert2rhel-0:0.17-1.el7.noarch", "pmajor": "8"}],
            [{"local_version": "0.25", "package_version": "convert2rhel-0:0.17-1.el7.noarch", "pmajor": "6"}],
            [{"local_version": "0.25", "package_version": "convert2rhel-0:0.17-1.el7.noarch", "pmajor": "7"}],
            [{"local_version": "0.25", "package_version": "convert2rhel-0:0.17-1.el7.noarch", "pmajor": "8"}],
            [{"local_version": "1.10", "package_version": "convert2rhel-0:0.18-1.el7.noarch", "pmajor": "8"}],
        ),
        indirect=True,
    )
    def test_c2r_up_to_date(self, caplog, monkeypatch, convert2rhel_latest_check, convert2rhel_latest_version_test):
        convert2rhel_latest_check.run()

        local_version, dummy_ = convert2rhel_latest_version_test
        log_msg = "Latest available Convert2RHEL version is installed."
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        ([{"local_version": "1.10", "package_version": "convert2rhel-0:0.18-1.el7.noarch", "pmajor": "8"}],),
        indirect=True,
    )
    def test_c2r_up_to_date_repoquery_error(
        self, caplog, monkeypatch, convert2rhel_latest_check, convert2rhel_latest_version_test
    ):
        monkeypatch.setattr(utils, "run_subprocess", mock.Mock(return_value=("Repoquery did not run", 1)))

        convert2rhel_latest_check.run()

        log_msg = (
            "Couldn't check if the current installed Convert2RHEL is the latest version.\n"
            "repoquery failed with the following output:\nRepoquery did not run"
        )
        assert log_msg in caplog.text

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        (
            [
                {
                    "local_version": "0.19",
                    "package_version": "convert2rhel-0:0.18-1.el7.noarch\nconvert2rhel-0:0.17-1.el7.noarch\nconvert2rhel-0:0.20-1.el7.noarch",
                    "pmajor": "8",
                }
            ],
        ),
        indirect=True,
    )
    def test_c2r_up_to_date_multiple_packages(
        self, caplog, convert2rhel_latest_check, convert2rhel_latest_version_test
    ):

        with pytest.raises(convert2rhel_latest.Convert2rhelLatestError) as exc_info:
            convert2rhel_latest_check.run()

        assert exc_info.value.code == "OUT_OF_DATE"

        local_version, package_version = convert2rhel_latest_version_test

        msg = (
            "You are currently running %s and the latest version of Convert2RHEL is 0.20.\n"
            "Only the latest version is supported for conversion. If you want to ignore"
            " this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue."
            % (local_version,)
        )
        assert exc_info.value.message == msg

    @pytest.mark.parametrize(
        ("convert2rhel_latest_version_test",),
        ([{"local_version": "0.17", "package_version": "convert2rhel-0:0.18-1.el7.noarch", "pmajor": "8"}],),
        indirect=True,
    )
    def test_c2r_up_to_date_deprecated_env_var(
        self, caplog, monkeypatch, convert2rhel_latest_check, convert2rhel_latest_version_test
    ):
        env = {"CONVERT2RHEL_UNSUPPORTED_VERSION": 1}
        monkeypatch.setattr(os, "environ", env)

        convert2rhel_latest_check.run()

        log_msg = (
            "You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_VERSION'"
            " environment variable.  Please switch to 'CONVERT2RHEL_ALLOW_OLDER_VERSION'"
            " instead."
        )

        assert log_msg in caplog.text
