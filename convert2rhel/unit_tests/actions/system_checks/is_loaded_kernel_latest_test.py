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

import os

from collections import namedtuple

import pytest
import six

from convert2rhel import actions, pkgmanager, unit_tests
from convert2rhel.actions.system_checks import is_loaded_kernel_latest
from convert2rhel.unit_tests import run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos7, centos8, oracle8
from convert2rhel.utils import run_subprocess


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def is_loaded_kernel_latest_action():
    return is_loaded_kernel_latest.IsLoadedKernelLatest()


class TestIsLoadedKernelLatest:
    @oracle8
    def test_is_loaded_kernel_latest_skip_on_not_latest_ol(
        self, pretend_os, caplog, is_loaded_kernel_latest_action, monkeypatch
    ):
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "eus_system", value=True)
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "has_internet_access", value=True)

        message = (
            "Skipping the check because there are no publicly available Oracle Linux Server 8.6 repositories available."
        )
        is_loaded_kernel_latest_action.run()

        assert message in caplog.records[-1].message

    @pytest.mark.parametrize(
        (
            "repoquery_version",
            "uname_version",
            "return_code",
            "package_name",
        ),
        (
            (
                "C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos",
                "3.10.0-1160.42.2.el7.x86_64",
                0,
                "kernel-core",
            ),
        ),
    )
    @centos8
    def test_is_loaded_kernel_latest_eus_system_invalid_kernel_version(
        self,
        pretend_os,
        repoquery_version,
        uname_version,
        return_code,
        package_name,
        tmpdir,
        monkeypatch,
        is_loaded_kernel_latest_action,
    ):
        fake_reposdir_path = str(tmpdir)
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "get_hardcoded_repofiles_dir",
            value=lambda: fake_reposdir_path,
        )

        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "has_internet_access", True)

        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        "--setopt=reposdir=%s" % fake_reposdir_path,
                        package_name,
                    ),
                    (
                        repoquery_version,
                        return_code,
                    ),
                ),
                (("uname", "-r"), (uname_version, return_code)),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest_action.run()

        unit_tests.assert_actions_result(
            is_loaded_kernel_latest_action,
            id="INVALID_KERNEL_VERSION",
            level="ERROR",
            title="Invalid kernel version detected",
            description="The loaded kernel version mismatch the latest one available in repositories defined in the %s folder"
            % fake_reposdir_path,
            diagnosis="The version of the loaded kernel is different from the latest version in repositories defined in the %s folder"
            % fake_reposdir_path,
            remediation="To proceed with the conversion, update the kernel version by executing the following step:\n\n",
        )

    @pytest.mark.parametrize(
        (
            "repoquery_version",
            "uname_version",
            "return_code",
            "package_name",
            "title",
            "description",
            "diagnosis",
            "remediation",
        ),
        (
            (
                "C2R\t1634146676\t1-1.01-5.02\tbaseos",
                "2-1.01-5.02",
                0,
                "kernel-core",
                "Invalid kernel package found",
                "Please refer to the diagnosis for further information",
                "The package names ('kernel-core-1' and 'kernel-core-2') do not match. Can only compare versions for the same packages.",
                None,
            ),
            (
                "C2R\t1634146676\t1 .01-5.02\tbaseos",
                "1 .01-5.03",
                0,
                "kernel-core",
                "Invalid kernel package found",
                "Please refer to the diagnosis for further information",
                "Invalid package - kernel-core-1 .01-5.02, packages need to be in one of the following formats: NEVRA, NEVR, NVRA, NVR, ENVRA, ENVR.",
                None,
            ),
        ),
    )
    @centos8
    @pytest.mark.skipif(pkgmanager.TYPE != "dnf", reason="cannot test dnf backend if dnf is not present")
    def test_is_loaded_kernel_latest_invalid_kernel_package_dnf(
        self,
        pretend_os,
        repoquery_version,
        uname_version,
        return_code,
        package_name,
        title,
        description,
        diagnosis,
        remediation,
        monkeypatch,
        is_loaded_kernel_latest_action,
    ):
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "has_internet_access", True)

        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        package_name,
                    ),
                    (
                        repoquery_version,
                        return_code,
                    ),
                ),
                (("uname", "-r"), (uname_version, return_code)),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest_action.run()
        unit_tests.assert_actions_result(
            is_loaded_kernel_latest_action,
            level="ERROR",
            id="INVALID_KERNEL_PACKAGE",
            title=title,
            description=description,
            diagnosis=diagnosis,
            remediation=remediation,
        )

    @pytest.mark.parametrize(
        (
            "repoquery_version",
            "uname_version",
            "return_code",
            "package_name",
            "title",
            "description",
            "diagnosis",
            "remediation",
        ),
        (
            (
                "C2R\t1634146676\t1-1.01-5.02\tbaseos",
                "2-1.01-5.02",
                0,
                "kernel",
                "Invalid kernel package found",
                "Please refer to the diagnosis for further information",
                "The following field(s) are invalid - release : 1.01-5",
                None,
            ),
            (
                "C2R\t1634146676\t1 .01-5.02\tbaseos",
                "1 .01-5.03",
                0,
                "kernel",
                "Invalid kernel package found",
                "Please refer to the diagnosis for further information",
                "The following field(s) are invalid - version : 1 .01",
                None,
            ),
        ),
    )
    @centos7
    @pytest.mark.skipif(pkgmanager.TYPE != "yum", reason="cannot test yum backend if yum is not present")
    def test_is_loaded_kernel_latest_invalid_kernel_package_yum(
        self,
        pretend_os,
        repoquery_version,
        uname_version,
        return_code,
        package_name,
        title,
        description,
        diagnosis,
        remediation,
        monkeypatch,
        is_loaded_kernel_latest_action,
    ):
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "has_internet_access", True)

        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        package_name,
                    ),
                    (
                        repoquery_version,
                        return_code,
                    ),
                ),
                (("uname", "-r"), (uname_version, return_code)),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest_action.run()

        unit_tests.assert_actions_result(
            is_loaded_kernel_latest_action,
            level="ERROR",
            id="INVALID_KERNEL_PACKAGE",
            title=title,
            description=description,
            diagnosis=diagnosis,
            remediation=remediation,
        )

    @centos8
    def test_is_loaded_kernel_latest_eus_system(
        self, pretend_os, tmpdir, monkeypatch, caplog, is_loaded_kernel_latest_action
    ):
        fake_reposdir_path = str(tmpdir)
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "get_hardcoded_repofiles_dir",
            value=lambda: fake_reposdir_path,
        )

        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "has_internet_access", True)

        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        "--setopt=reposdir=%s" % fake_reposdir_path,
                        "kernel-core",
                    ),
                    (
                        "C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos",
                        0,
                    ),
                ),
                (("uname", "-r"), ("3.10.0-1160.45.1.el7.x86_64", 0)),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest_action.run()
        assert "The currently loaded kernel is at the latest version." in caplog.records[-1].message

    @centos8
    def test_is_loaded_kernel_latest_eus_system_no_connection(
        self, pretend_os, monkeypatch, tmpdir, caplog, is_loaded_kernel_latest_action
    ):
        monkeypatch.setattr(is_loaded_kernel_latest, "get_hardcoded_repofiles_dir", value=lambda: str(tmpdir))
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "has_internet_access", False)
        expected = set(
            (
                actions.ActionMessage(
                    level="WARNING",
                    id="IS_LOADED_KERNEL_LATEST_CHECK_SKIP",
                    title="Skipping the is loaded kernel latest check",
                    description="Skipping the check as no internet connection has been detected.",
                    diagnosis=None,
                    remediation=None,
                ),
            )
        )

        is_loaded_kernel_latest_action.run()
        assert "Skipping the check as no internet connection has been detected." in caplog.records[-1].message
        assert expected.issuperset(is_loaded_kernel_latest_action.messages)
        assert expected.issubset(is_loaded_kernel_latest_action.messages)

    @centos8
    @pytest.mark.parametrize(
        (
            "repoquery_stdout",
            "return_code",
            "unsupported_skip",
            "skip_check",
            "level",
            "id",
            "title",
            "description",
            "diagnosis",
            "remediation",
        ),
        (
            pytest.param(
                "",
                0,
                "0",
                "1",
                "WARNING",
                "UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK_DETECTED",
                "Skipping the kernel currency check",
                (
                    "Detected 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK' environment variable, we will skip the kernel-core comparison.\nBeware, this could leave your system in a broken state."
                ),
                None,
                None,
                id="Unsupported skip with environment var set to 1",
            ),
        ),
    )
    def test_is_loaded_kernel_latest_skip_warnings(
        self,
        pretend_os,
        repoquery_stdout,
        return_code,
        unsupported_skip,
        skip_check,
        level,
        id,
        title,
        description,
        diagnosis,
        remediation,
        monkeypatch,
        caplog,
        is_loaded_kernel_latest_action,
    ):
        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        "kernel-core",
                    ),
                    (
                        repoquery_stdout,
                        return_code,
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )
        monkeypatch.setattr(
            os,
            "environ",
            {"CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK": unsupported_skip},
        )
        monkeypatch.setattr(
            os,
            "environ",
            {"CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK": skip_check},
        )

        expected_set = set(
            (
                actions.ActionMessage(
                    level=level,
                    id=id,
                    title=title,
                    description=description,
                    diagnosis=diagnosis,
                    remediation=remediation,
                ),
            )
        )
        is_loaded_kernel_latest_action.run()
        assert description in caplog.records[-1].message
        assert expected_set.issuperset(is_loaded_kernel_latest_action.messages)
        assert expected_set.issubset(is_loaded_kernel_latest_action.messages)

    @centos8
    @pytest.mark.parametrize(
        (
            "repoquery_stdout",
            "return_code",
            "unsupported_skip",
            "latest_skip",
            "level",
            "id",
            "title",
            "description",
            "unsupported_message",
            "diagnosis",
            "remediation",
        ),
        (
            pytest.param(
                "",
                0,
                "1",
                "0",
                "WARNING",
                "UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK_DETECTED_1",
                "Skipping the kernel currency check",
                (
                    "Detected 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK' environment variable, we will skip the kernel-core comparison.\nBeware, this could leave your system in a broken state."
                ),
                (
                    "You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' environment variable. Please switch to 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK' instead."
                ),
                None,
                None,
                id="Unsupported skip with environment var set to 1",
            ),
        ),
    )
    def test_is_loaded_kernel_latest_unsupported_skip_warning(
        self,
        pretend_os,
        repoquery_stdout,
        return_code,
        unsupported_skip,
        latest_skip,
        level,
        id,
        title,
        description,
        unsupported_message,
        diagnosis,
        remediation,
        monkeypatch,
        caplog,
        is_loaded_kernel_latest_action,
    ):
        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        "kernel-core",
                    ),
                    (
                        repoquery_stdout,
                        return_code,
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )
        monkeypatch.setattr(
            os,
            "environ",
            {"CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK": unsupported_skip},
        )
        monkeypatch.setattr(
            os,
            "environ",
            {"CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK": latest_skip},
        )

        expected_set = set(
            (
                actions.ActionMessage(
                    level=level,
                    id=id,
                    title=title,
                    description=description,
                    diagnosis=diagnosis,
                    remediation=remediation,
                ),
            )
        )
        is_loaded_kernel_latest_action.run()
        assert unsupported_message in caplog.records[-1].message
        assert expected_set.issuperset(is_loaded_kernel_latest_action.messages)
        assert expected_set.issubset(is_loaded_kernel_latest_action.messages)

    @centos8
    @pytest.mark.parametrize(
        (
            "repoquery_stdout",
            "return_code",
            "level",
            "id",
            "title",
            "description",
            "diagnosis",
            "remediation",
        ),
        (
            pytest.param(
                "",
                1,
                "WARNING",
                "UNABLE_TO_FETCH_RECENT_KERNELS",
                "Unable to fetch recent kernels",
                (
                    "Couldn't fetch the list of the most recent kernels available in "
                    "the repositories. Skipping the loaded kernel check."
                ),
                None,
                None,
                id="Unsupported skip with environment var not set",
            ),
        ),
    )
    def test_is_loaded_kernel_latest_unable_to_fetch_kernels(
        self,
        pretend_os,
        repoquery_stdout,
        return_code,
        level,
        id,
        title,
        description,
        diagnosis,
        remediation,
        monkeypatch,
        caplog,
        is_loaded_kernel_latest_action,
    ):
        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        "kernel-core",
                    ),
                    (
                        repoquery_stdout,
                        return_code,
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        expected_set = set(
            (
                actions.ActionMessage(
                    level=level,
                    id=id,
                    title=title,
                    description=description,
                    diagnosis=diagnosis,
                    remediation=remediation,
                ),
            )
        )
        is_loaded_kernel_latest_action.run()
        assert description in caplog.records[-1].message
        assert expected_set.issuperset(is_loaded_kernel_latest_action.messages)
        assert expected_set.issubset(is_loaded_kernel_latest_action.messages)

    @centos8
    @pytest.mark.parametrize(
        (
            "repoquery_version",
            "return_code",
            "package_name",
            "title",
            "description",
            "diagnosis",
            "remediation",
        ),
        (
            pytest.param(
                "",
                0,
                "kernel-core",
                "Kernel currency check failed",
                "Please refer to the diagnosis for further information",
                "Could not find any {0} from repositories to compare against the loaded kernel.",
                "Please, check if you have any vendor repositories enabled to proceed with the conversion.\nIf you wish to ignore this message, set the environment variable 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' to 1.",
                id="Repoquery failure without environment var",
            ),
        ),
    )
    def test_is_loaded_kernel_latest_unsupported_skip_error(
        self,
        pretend_os,
        repoquery_version,
        return_code,
        package_name,
        title,
        description,
        remediation,
        diagnosis,
        monkeypatch,
        is_loaded_kernel_latest_action,
    ):
        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        package_name,
                    ),
                    (
                        repoquery_version,
                        return_code,
                    ),
                ),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )
        is_loaded_kernel_latest_action.run()
        diagnosis = diagnosis.format(package_name)
        unit_tests.assert_actions_result(
            is_loaded_kernel_latest_action,
            level="ERROR",
            id="KERNEL_CURRENCY_CHECK_FAIL",
            title=title,
            description=description,
            diagnosis=diagnosis,
            remediation=remediation,
        )

    @pytest.mark.parametrize(
        (
            "repoquery_version",
            "uname_version",
            "return_code",
            "major_ver",
            "package_name",
            "expected_message",
        ),
        (
            (
                "C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos",
                "3.10.0-1160.42.2.el7.x86_64",
                1,
                8,
                "kernel-core",
                "Couldn't fetch the list of the most recent kernels available in the repositories.",
            ),
            (
                "C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos",
                "3.10.0-1160.45.1.el7.x86_64",
                0,
                7,
                "kernel",
                "The currently loaded kernel is at the latest version.",
            ),
            (
                """
                Repository base is listed more than once in the configuration\n
                Repository updates is listed more than once in the configuration\n
                Repository extras is listed more than once in the configuration\n
                Repository centosplus is listed more than once in the configuration\n
                C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos\n
                Could not retrieve mirrorlist http://mirorlist.centos.org/?release=7&arch=x86_64&repo=os&infra=stock error was\n
                14: curl#6 - "Could not resolve host: mirorlist.centos.org; Unknown error"\n
                Repo convert2rhel-for-rhel-7-rpms forced skip_if_unavailable=True due to: /etc/rhsm/ca/redhat-uep.pem\n
                """,
                "3.10.0-1160.45.1.el7.x86_64",
                0,
                8,
                "kernel-core",
                "The currently loaded kernel is at the latest version.",
            ),
            (
                """
                gargabe-output before the good line\n
                C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos\n
                more garbage\n
                """,
                "3.10.0-1160.45.1.el7.x86_64",
                0,
                8,
                "kernel-core",
                "The currently loaded kernel is at the latest version.",
            ),
        ),
    )
    def test_is_loaded_kernel_latest(
        self,
        repoquery_version,
        uname_version,
        return_code,
        major_ver,
        package_name,
        expected_message,
        monkeypatch,
        caplog,
        is_loaded_kernel_latest_action,
    ):
        # Using the minor version as 99, so the tests should never fail because of a
        # constraint in the code, since we don't mind the minor version number (for
        # now), and require only that the major version to be in the range of 6 to
        # 8, we can set the minor version to 99 to avoid hardcoded checks in the
        # code.
        Version = namedtuple("Version", ("major", "minor"))
        monkeypatch.setattr(
            is_loaded_kernel_latest.system_info,
            "version",
            value=Version(major=major_ver, minor=99),
        )
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "id", "centos")
        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        package_name,
                    ),
                    (
                        repoquery_version,
                        return_code,
                    ),
                ),
                (("uname", "-r"), (uname_version, return_code)),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest_action.run()
        assert expected_message in caplog.records[-1].message

    def test_is_loaded_kernel_latest_system_exit(self, monkeypatch, caplog, is_loaded_kernel_latest_action):
        repoquery_version = "C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos"
        uname_version = "3.10.0-1160.42.2.el7.x86_64"

        # Using the minor version as 99, so the tests should never fail because of a
        # constraint in the code, since we don't mind the minor version number (for
        # now), and require only that the major version to be in the range of 6 to
        # 8, we can set the minor version to 99 to avoid hardcoded checks in the
        # code.
        Version = namedtuple("Version", ("major", "minor"))
        monkeypatch.setattr(
            is_loaded_kernel_latest.system_info,
            "version",
            value=Version(major=8, minor=99),
        )
        monkeypatch.setattr(is_loaded_kernel_latest.system_info, "id", "centos")
        run_subprocess_mocked = mock.Mock(
            spec=run_subprocess,
            side_effect=run_subprocess_side_effect(
                (
                    (
                        "repoquery",
                        "--setopt=exclude=",
                        "--quiet",
                        "--qf",
                        "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
                        "kernel-core",
                    ),
                    (
                        repoquery_version,
                        0,
                    ),
                ),
                (("uname", "-r"), (uname_version, 0)),
            ),
        )
        monkeypatch.setattr(
            is_loaded_kernel_latest,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest_action.run()
        unit_tests.assert_actions_result(
            is_loaded_kernel_latest_action,
            level="ERROR",
            id="INVALID_KERNEL_VERSION",
            title="Invalid kernel version detected",
            description="The loaded kernel version mismatch the latest one available in the enabled system repositories",
            diagnosis="The version of the loaded kernel is different from the latest version in the enabled system repositories.",
            remediation="To proceed with the conversion, update the kernel version by executing the following step:",
        )
