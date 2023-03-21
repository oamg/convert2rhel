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
import os.path
import re
import unittest

from collections import namedtuple

import pytest
import six

from convert2rhel import actions, grub, pkgmanager, unit_tests
from convert2rhel.actions import (
    _bad_kernel_package_signature,
    _bad_kernel_substring,
    _bad_kernel_version,
    get_loaded_kmods,
    is_loaded_kernel_latest,
)
from convert2rhel.pkghandler import get_pkg_fingerprint
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import GetFileContentMocked, GetLoggerMocked, run_subprocess_side_effect
from convert2rhel.unit_tests.conftest import centos7, centos8, oracle8
from convert2rhel.utils import run_subprocess


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


MODINFO_STUB = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
)

HOST_MODULES_STUB_GOOD = frozenset(
    (
        "kernel/lib/a.ko.xz",
        "kernel/lib/b.ko.xz",
        "kernel/lib/c.ko.xz",
    )
)
HOST_MODULES_STUB_BAD = frozenset(
    (
        "kernel/lib/d.ko.xz",
        "kernel/lib/e.ko.xz",
        "kernel/lib/f.ko.xz",
    )
)

REPOQUERY_F_STUB_GOOD = (
    "kernel-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
)
REPOQUERY_F_STUB_BAD = (
    "kernel-idontexpectyou-core-sdsdsd.ell8_3.x86_64\n"
    "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64\n"
    "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64\n"
)
REPOQUERY_L_STUB_GOOD = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko\n"
)
REPOQUERY_L_STUB_BAD = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/e.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko\n"
)


def test_perform_pre_checks(monkeypatch):
    check_thirdparty_kmods_mock = mock.Mock()
    check_custom_repos_are_valid_mock = mock.Mock()
    is_loaded_kernel_latest_mock = mock.Mock()
    check_dbus_is_running_mock = mock.Mock()

    monkeypatch.setattr(
        actions,
        "check_tainted_kmods",
        value=check_thirdparty_kmods_mock,
    )
    monkeypatch.setattr(
        actions,
        "check_custom_repos_are_valid",
        value=check_custom_repos_are_valid_mock,
    )
    monkeypatch.setattr(
        actions,
        "check_custom_repos_are_valid",
        value=check_custom_repos_are_valid_mock,
    )
    monkeypatch.setattr(actions, "is_loaded_kernel_latest", value=is_loaded_kernel_latest_mock)
    monkeypatch.setattr(actions, "check_dbus_is_running", value=check_dbus_is_running_mock)

    actions.perform_system_checks()

    check_thirdparty_kmods_mock.assert_called_once()
    is_loaded_kernel_latest_mock.assert_called_once()
    check_dbus_is_running_mock.assert_called_once()


def test_perform_pre_ponr_checks(monkeypatch):
    ensure_compatibility_of_kmods_mock = mock.Mock()
    create_transaction_handler_mock = mock.Mock()
    monkeypatch.setattr(
        actions,
        "ensure_compatibility_of_kmods",
        value=ensure_compatibility_of_kmods_mock,
    )
    monkeypatch.setattr(
        actions.pkgmanager,
        "create_transaction_handler",
        value=create_transaction_handler_mock,
    )
    actions.perform_pre_ponr_checks()
    ensure_compatibility_of_kmods_mock.assert_called_once()
    create_transaction_handler_mock.assert_called_once()


@pytest.mark.parametrize(
    (
        "host_kmods",
        "exception",
        "should_be_in_logs",
        "shouldnt_be_in_logs",
    ),
    (
        (
            HOST_MODULES_STUB_GOOD,
            None,
            "loaded kernel modules are available in RHEL",
            None,
        ),
        (
            HOST_MODULES_STUB_BAD,
            SystemExit,
            None,
            "loaded kernel modules are available in RHEL",
        ),
    ),
)
@centos8
def test_ensure_compatibility_of_kmods(
    monkeypatch,
    pretend_os,
    caplog,
    host_kmods,
    exception,
    should_be_in_logs,
    shouldnt_be_in_logs,
):
    monkeypatch.setattr(actions, "get_loaded_kmods", mock.Mock(return_value=host_kmods))
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        actions,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    if exception:
        with pytest.raises(exception):
            actions.ensure_compatibility_of_kmods()
    else:
        actions.ensure_compatibility_of_kmods()

    if should_be_in_logs:
        assert should_be_in_logs in caplog.records[-1].message
    if shouldnt_be_in_logs:
        assert shouldnt_be_in_logs not in caplog.records[-1].message


@centos8
def test_ensure_compatibility_of_kmods_check_env(
    monkeypatch,
    pretend_os,
    caplog,
):

    monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS": "1"})
    monkeypatch.setattr(actions, "get_loaded_kmods", mock.Mock(return_value=HOST_MODULES_STUB_BAD))
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        actions,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    actions.ensure_compatibility_of_kmods()
    should_be_in_logs = (
        ".*Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable."
        " We will continue the conversion with the following kernel modules unavailable in RHEL:.*"
    )
    assert re.match(pattern=should_be_in_logs, string=caplog.records[-1].message, flags=re.MULTILINE | re.DOTALL)


@pytest.mark.parametrize(
    (
        "unsupported_pkg",
        "msg_in_logs",
        "msg_not_in_logs",
        "exception",
    ),
    (
        # ff-memless specified to be ignored in the config, so no exception raised
        (
            "kernel/drivers/input/ff-memless.ko.xz",
            "loaded kernel modules are available in RHEL",
            "The following loaded kernel modules are not available in RHEL",
            None,
        ),
        (
            "kernel/drivers/input/other.ko.xz",
            "The following loaded kernel modules are not available in RHEL",
            None,
            SystemExit,
        ),
    ),
)
@centos7
def test_ensure_compatibility_of_kmods_excluded(
    monkeypatch,
    pretend_os,
    caplog,
    unsupported_pkg,
    msg_in_logs,
    msg_not_in_logs,
    exception,
):
    monkeypatch.setattr(
        actions,
        "get_loaded_kmods",
        mock.Mock(
            return_value=HOST_MODULES_STUB_GOOD | frozenset((unsupported_pkg,)),
        ),
    )
    get_unsupported_kmods_mocked = mock.Mock(wraps=actions.get_unsupported_kmods)
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("repoquery", "-f"), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", "-l"), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        actions,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(
        actions,
        "get_unsupported_kmods",
        value=get_unsupported_kmods_mocked,
    )
    if exception:
        with pytest.raises(exception):
            actions.ensure_compatibility_of_kmods()
    else:
        actions.ensure_compatibility_of_kmods()

    get_unsupported_kmods_mocked.assert_called_with(
        # host kmods
        set(
            (
                unsupported_pkg,
                "kernel/lib/c.ko.xz",
                "kernel/lib/a.ko.xz",
                "kernel/lib/b.ko.xz",
            )
        ),
        # rhel supported kmods
        set(
            (
                "kernel/lib/c.ko",
                "kernel/lib/b.ko.xz",
                "kernel/lib/c.ko.xz",
                "kernel/lib/a.ko.xz",
                "kernel/lib/a.ko",
            )
        ),
    )
    if msg_in_logs:
        assert any(msg_in_logs in record.message for record in caplog.records)
    if msg_not_in_logs:
        assert all(msg_not_in_logs not in record.message for record in caplog.records)


def test_get_loaded_kmods(monkeypatch):
    run_subprocess_mocked = mock.Mock(
        spec=run_subprocess,
        side_effect=run_subprocess_side_effect(
            (
                ("lsmod",),
                (
                    "Module                  Size  Used by\n"
                    "a                 81920  4\n"
                    "b    49152  0\n"
                    "c              40960  1\n",
                    0,
                ),
            ),
            (
                ("modinfo", "-F", "filename", "a"),
                (MODINFO_STUB.split()[0] + "\n", 0),
            ),
            (
                ("modinfo", "-F", "filename", "b"),
                (MODINFO_STUB.split()[1] + "\n", 0),
            ),
            (
                ("modinfo", "-F", "filename", "c"),
                (MODINFO_STUB.split()[2] + "\n", 0),
            ),
        ),
    )
    monkeypatch.setattr(
        actions,
        "run_subprocess",
        value=run_subprocess_mocked,
    )
    assert get_loaded_kmods() == frozenset(("kernel/lib/c.ko.xz", "kernel/lib/a.ko.xz", "kernel/lib/b.ko.xz"))


@pytest.mark.parametrize(
    ("repoquery_f_stub", "repoquery_l_stub"),
    (
        (REPOQUERY_F_STUB_GOOD, REPOQUERY_L_STUB_GOOD),
        (REPOQUERY_F_STUB_BAD, REPOQUERY_L_STUB_GOOD),
    ),
)
@centos8
def test_get_rhel_supported_kmods(
    monkeypatch,
    pretend_os,
    repoquery_f_stub,
    repoquery_l_stub,
):
    run_subprocess_mock = mock.Mock(
        side_effect=run_subprocess_side_effect(
            (
                ("repoquery", "-f"),
                (repoquery_f_stub, 0),
            ),
            (
                ("repoquery", "-l"),
                (repoquery_l_stub, 0),
            ),
        )
    )
    monkeypatch.setattr(
        actions,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    res = actions.get_rhel_supported_kmods()
    assert res == set(
        (
            "kernel/lib/a.ko",
            "kernel/lib/a.ko.xz",
            "kernel/lib/b.ko.xz",
            "kernel/lib/c.ko.xz",
            "kernel/lib/c.ko",
        )
    )


@pytest.mark.parametrize(
    ("pkgs", "exp_res"),
    (
        (
            (
                "kernel-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kernel-debug-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel-debug-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
        ),
        (
            (
                "kmod-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kmod-core-0:10.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:9.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:10.18.0-240.10.1.el8_3.x86_64",),
        ),
        (
            (
                "not-expected-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kernel-core-0:4.18.0-240.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kernel-core-0:4.18.0-240.15.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",),
        ),
        (
            (
                "kernel-core-0:4.18.0-240.16.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.16.beta5.1.el8_3.x86_64",),
        ),
        (("kernel_bad_package:111111",), ("kernel_bad_package:111111",)),
        (
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel_bad_package:111111",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel_bad_package:111111",
            ),
        ),
    ),
)
def test_get_most_recent_unique_kernel_pkgs(pkgs, exp_res):
    assert tuple(actions.get_most_recent_unique_kernel_pkgs(pkgs)) == exp_res


@pytest.mark.parametrize(
    ("command_return", "expected_exception"),
    (
        (
            ("", 0),
            None,
        ),
        (
            (
                (
                    "system76_io 16384 0 - Live 0x0000000000000000 (OE)\n"
                    "system76_acpi 16384 0 - Live 0x0000000000000000 (OE)"
                ),
                0,
            ),
            SystemExit,
        ),
    ),
)
def test_check_tainted_kmods(monkeypatch, command_return, expected_exception):
    run_subprocess_mock = mock.Mock(return_value=command_return)
    monkeypatch.setattr(
        actions,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    if expected_exception:
        with pytest.raises(expected_exception):
            actions.check_tainted_kmods()
    else:
        actions.check_tainted_kmods()


class CallYumCmdMocked(unit_tests.MockFunction):
    def __init__(self, ret_code, ret_string):
        self.called = 0
        self.return_code = ret_code
        self.return_string = ret_string
        self.fail_once = False
        self.command = None

    def __call__(self, command, *args, **kwargs):
        if self.fail_once and self.called == 0:
            self.return_code = 1
        if self.fail_once and self.called > 0:
            self.return_code = 0
        self.called += 1
        self.command = command
        return self.return_string, self.return_code


class TestCustomReposAreValid(unittest.TestCase):
    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(
        actions,
        "call_yum_cmd",
        CallYumCmdMocked(ret_code=0, ret_string="Abcdef"),
    )
    @unit_tests.mock(actions, "logger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "no_rhsm", True)
    def test_custom_repos_are_valid(self):
        actions.check_custom_repos_are_valid()
        self.assertEqual(len(actions.logger.info_msgs), 1)
        self.assertEqual(len(actions.logger.debug_msgs), 1)
        self.assertIn(
            "The repositories passed through the --enablerepo option are all accessible.", actions.logger.info_msgs
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(
        actions,
        "call_yum_cmd",
        CallYumCmdMocked(ret_code=1, ret_string="Abcdef"),
    )
    @unit_tests.mock(actions, "logger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "no_rhsm", True)
    def test_custom_repos_are_invalid(self):
        self.assertRaises(SystemExit, actions.check_custom_repos_are_valid)
        self.assertEqual(len(actions.logger.critical_msgs), 1)
        self.assertEqual(len(actions.logger.info_msgs), 0)
        self.assertIn("Unable to access the repositories passed through ", actions.logger.critical_msgs[0])


class TestIsLoadedKernelLatest:
    @oracle8
    def test_is_loaded_kernel_latest_skip_on_not_latest_ol(
        self,
        pretend_os,
        caplog,
    ):
        message = (
            "Skipping the check because there are no publicly available Oracle Linux Server 8.4 repositories available."
        )

        is_loaded_kernel_latest()

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
    def test_is_loaded_kernel_latest_eus_system_system_exit(
        self,
        pretend_os,
        repoquery_version,
        uname_version,
        return_code,
        package_name,
        tmpdir,
        monkeypatch,
        caplog,
    ):
        fake_reposdir_path = str(tmpdir)
        monkeypatch.setattr(
            actions,
            "get_hardcoded_repofiles_dir",
            value=lambda: fake_reposdir_path,
        )

        monkeypatch.setattr(actions.system_info, "has_internet_access", True)

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
            actions,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        with pytest.raises(SystemExit):
            is_loaded_kernel_latest()

        repoquery_kernel_version = repoquery_version.split("\t")[2]
        uname_kernel_version = uname_version.rsplit(".", 1)[0]
        assert (
            "The version of the loaded kernel is different from the latest version in repositories defined in the %s folder"
            % fake_reposdir_path
        )
        assert (
            "Latest kernel version available in baseos: %s\n" % repoquery_kernel_version in caplog.records[-1].message
        )
        assert "Loaded kernel version: %s\n" % uname_kernel_version in caplog.records[-1].message

    @centos8
    def test_is_loaded_kernel_latest_eus_system(self, pretend_os, tmpdir, monkeypatch, caplog):
        fake_reposdir_path = str(tmpdir)
        monkeypatch.setattr(
            actions,
            "get_hardcoded_repofiles_dir",
            value=lambda: fake_reposdir_path,
        )

        monkeypatch.setattr(actions.system_info, "has_internet_access", True)

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
            actions,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest()
        assert "The currently loaded kernel is at the latest version." in caplog.records[-1].message

    @centos8
    def test_is_loaded_kernel_latest_eus_system_no_connection(self, pretend_os, monkeypatch, tmpdir, caplog):
        monkeypatch.setattr(actions, "get_hardcoded_repofiles_dir", value=lambda: str(tmpdir))
        system_info.has_internet_access = False

        is_loaded_kernel_latest()
        assert "Skipping the check as no internet connection has been detected." in caplog.records[-1].message

    @centos8
    @pytest.mark.parametrize(
        (
            "repoquery_version",
            "return_code",
            "package_name",
            "unsupported_skip",
            "expected",
        ),
        (
            pytest.param(
                "",
                0,
                "kernel-core",
                "1",
                "Detected 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' environment variable",
                id="Unsupported skip with environment var set to 1",
            ),
            pytest.param(
                "",
                0,
                "kernel-core",
                "0",
                "Detected 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' environment variable",
                id="Unsupported skip with environment var set to 0",
            ),
            pytest.param(
                "",
                0,
                "kernel-core",
                None,
                "Could not find any {0} from repositories to compare against the loaded kernel.",
                id="Repoquery failure without environment var",
            ),
        ),
    )
    def test_is_loaded_kernel_latest_unsupported_skip(
        self,
        pretend_os,
        repoquery_version,
        return_code,
        package_name,
        unsupported_skip,
        expected,
        monkeypatch,
        caplog,
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
            actions,
            "run_subprocess",
            value=run_subprocess_mocked,
        )
        if unsupported_skip:
            monkeypatch.setattr(
                os,
                "environ",
                {"CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK": unsupported_skip},
            )

        if not unsupported_skip:
            with pytest.raises(SystemExit):
                is_loaded_kernel_latest()
            expected = expected.format(package_name)
        else:
            is_loaded_kernel_latest()

        assert expected in caplog.records[-1].message

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
    ):
        # Using the minor version as 99, so the tests should never fail because of a
        # constraint in the code, since we don't mind the minor version number (for
        # now), and require only that the major version to be in the range of 6 to
        # 8, we can set the minor version to 99 to avoid hardcoded actions in the
        # code.
        Version = namedtuple("Version", ("major", "minor"))
        monkeypatch.setattr(
            actions.system_info,
            "version",
            value=Version(major=major_ver, minor=99),
        )
        system_info.id = "centos"
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
            actions,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        is_loaded_kernel_latest()
        assert expected_message in caplog.records[-1].message

    def test_is_loaded_kernel_latest_system_exit(self, monkeypatch, caplog):
        repoquery_version = "C2R\t1634146676\t3.10.0-1160.45.1.el7\tbaseos"
        uname_version = "3.10.0-1160.42.2.el7.x86_64"

        # Using the minor version as 99, so the tests should never fail because of a
        # constraint in the code, since we don't mind the minor version number (for
        # now), and require only that the major version to be in the range of 6 to
        # 8, we can set the minor version to 99 to avoid hardcoded actions in the
        # code.
        Version = namedtuple("Version", ("major", "minor"))
        monkeypatch.setattr(
            actions.system_info,
            "version",
            value=Version(major=8, minor=99),
        )
        system_info.id = "centos"
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
            actions,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        with pytest.raises(SystemExit):
            is_loaded_kernel_latest()

        repoquery_kernel_version = repoquery_version.split("\t")[2]
        uname_kernel_version = uname_version.rsplit(".", 1)[0]
        assert "Latest kernel version available in baseos: %s" % repoquery_kernel_version in caplog.records[-1].message
        assert "Loaded kernel version: %s\n\n" % uname_kernel_version in caplog.records[-1].message


@pytest.mark.parametrize(
    ("no_rhsm", "dbus_running", "log_msg"),
    (
        (True, True, "Skipping the check because we have been asked not to subscribe this system to RHSM."),
        (True, False, "Skipping the check because we have been asked not to subscribe this system to RHSM."),
        (False, True, "DBus Daemon is running"),
    ),
)
def test_check_dbus_is_running(
    caplog, monkeypatch, global_tool_opts, global_system_info, no_rhsm, dbus_running, log_msg
):
    monkeypatch.setattr(actions, "tool_opts", global_tool_opts)
    global_tool_opts.no_rhsm = no_rhsm
    monkeypatch.setattr(actions, "system_info", global_system_info)
    global_system_info.dbus_running = dbus_running

    assert actions.check_dbus_is_running() is None
    assert caplog.records[-1].message == log_msg

    assert log_msg == caplog.records[-1].message


def test_check_dbus_is_running_not_running(caplog, monkeypatch, global_tool_opts, global_system_info):
    monkeypatch.setattr(actions, "tool_opts", global_tool_opts)
    global_tool_opts.no_rhsm = False
    monkeypatch.setattr(actions, "system_info", global_system_info)
    global_system_info.dbus_running = False

    with pytest.raises(SystemExit):
        actions.check_dbus_is_running()

    log_msg = (
        "Could not find a running DBus Daemon which is needed to"
        " register with subscription manager.\nPlease start dbus using `systemctl"
        " start dbus`"
    )
    assert log_msg == caplog.records[-1].message
    assert caplog.records[-1].levelname == "CRITICAL"
