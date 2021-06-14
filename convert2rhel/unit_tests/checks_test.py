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

import os
import subprocess
import sys

from collections import namedtuple

import pytest

from convert2rhel import checks, unit_tests
from convert2rhel.checks import (
    _bad_kernel_package_signature,
    _bad_kernel_substring,
    _bad_kernel_version,
    _get_kmod_comparison_key,
    check_rhel_compatible_kernel_is_used,
    check_tainted_kmods,
    ensure_compatibility_of_kmods,
    get_installed_kmods,
    get_most_recent_unique_kernel_pkgs,
    get_rhel_supported_kmods,
    perform_pre_checks,
    perform_pre_ponr_checks,
)
from convert2rhel.pkghandler import get_pkg_fingerprint
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.unit_tests import GetFileContentMocked, GetLoggerMocked
from convert2rhel.utils import run_subprocess


try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest


try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest


if sys.version_info[:2] <= (2, 7):
    import mock  # pylint: disable=import-error
else:
    from unittest import mock  # pylint: disable=no-name-in-module


HOST_MODULES_STUB_GOOD = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/b.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/c.ko.xz\n"
)
HOST_MODULES_STUB_BAD = (
    "/lib/modules/5.8.0-7642-generic/kernel/lib/d.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/e.ko.xz\n"
    "/lib/modules/5.8.0-7642-generic/kernel/lib/f.ko.xz\n"
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


def _run_subprocess_side_effect(*stubs):
    def factory(*args, **kwargs):
        for kws, result in stubs:
            if all(kw in args[0] for kw in kws):
                return result
        else:
            return run_subprocess(*args, **kwargs)

    return factory


def test_perform_pre_checks(monkeypatch):
    check_thirdparty_kmods_mock = mock.Mock()
    check_uefi_mock = mock.Mock()
    check_readonly_mounts_mock = mock.Mock()
    check_custom_repos_are_valid_mock = mock.Mock()
    check_rhel_compatible_kernel_is_used_mock = mock.Mock()
    monkeypatch.setattr(
        checks,
        "check_uefi",
        value=check_uefi_mock,
    )
    monkeypatch.setattr(
        checks,
        "check_tainted_kmods",
        value=check_thirdparty_kmods_mock,
    )
    monkeypatch.setattr(
        checks,
        "check_readonly_mounts",
        value=check_readonly_mounts_mock,
    )
    monkeypatch.setattr(
        checks,
        "check_rhel_compatible_kernel_is_used",
        value=check_rhel_compatible_kernel_is_used_mock,
    )
    monkeypatch.setattr(
        checks,
        "check_custom_repos_are_valid",
        value=check_custom_repos_are_valid_mock,
    )

    perform_pre_checks()

    check_thirdparty_kmods_mock.assert_called_once()
    check_uefi_mock.assert_called_once()
    check_readonly_mounts_mock.assert_called_once()
    check_rhel_compatible_kernel_is_used_mock.assert_called_once()


def test_pre_ponr_checks(monkeypatch):
    ensure_compatibility_of_kmods_mock = mock.Mock()
    monkeypatch.setattr(
        checks,
        "ensure_compatibility_of_kmods",
        value=ensure_compatibility_of_kmods_mock,
    )
    perform_pre_ponr_checks()
    ensure_compatibility_of_kmods_mock.assert_called_once()


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
            "Kernel modules are compatible",
            None,
        ),
        (
            HOST_MODULES_STUB_BAD,
            SystemExit,
            None,
            "Kernel modules are compatible",
        ),
    ),
)
def test_ensure_compatibility_of_kmods(
    monkeypatch,
    pretend_centos8,
    caplog,
    host_kmods,
    exception,
    should_be_in_logs,
    shouldnt_be_in_logs,
):
    run_subprocess_mock = mock.Mock(
        side_effect=_run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("find",), (host_kmods, 0)),
            (("repoquery", " -f "), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", " -l "), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )

    if exception:
        with pytest.raises(exception):
            ensure_compatibility_of_kmods()
    else:
        ensure_compatibility_of_kmods()

    if should_be_in_logs:
        assert should_be_in_logs in caplog.records[-1].message
    if shouldnt_be_in_logs:
        assert shouldnt_be_in_logs not in caplog.records[-1].message


@pytest.mark.parametrize(
    (
        "unsupported_pkg",
        "msg_in_logs",
        "msg_not_in_logs",
        "exception",
    ),
    (
        (
            "/lib/modules/3.10.0-1160.6.1/kernel/drivers/input/ff-memless.ko.xz\n",
            "Kernel modules are compatible",
            "The following kernel modules are not supported in RHEL",
            None,
        ),
        (
            "/lib/modules/3.10.0-1160.6.1/kernel/drivers/input/other.ko.xz\n",
            "The following kernel modules are not supported in RHEL",
            None,
            SystemExit,
        ),
    ),
)
def test_ensure_compatibility_of_kmods_excluded(
    monkeypatch,
    pretend_centos7,
    caplog,
    unsupported_pkg,
    msg_in_logs,
    msg_not_in_logs,
    exception,
):
    get_unsupported_kmods_mocked = mock.Mock(wraps=checks.get_unsupported_kmods)
    run_subprocess_mock = mock.Mock(
        side_effect=_run_subprocess_side_effect(
            (("uname",), ("5.8.0-7642-generic\n", 0)),
            (("find",), (HOST_MODULES_STUB_GOOD + unsupported_pkg, 0)),
            (("repoquery", " -f "), (REPOQUERY_F_STUB_GOOD, 0)),
            (("repoquery", " -l "), (REPOQUERY_L_STUB_GOOD, 0)),
        )
    )
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    monkeypatch.setattr(
        checks,
        "get_unsupported_kmods",
        value=get_unsupported_kmods_mocked,
    )
    if exception:
        with pytest.raises(exception):
            ensure_compatibility_of_kmods()
    else:
        ensure_compatibility_of_kmods()
    get_unsupported_kmods_mocked.assert_called_with(
        # host kmods
        set(
            (
                _get_kmod_comparison_key(unsupported_pkg.rstrip()),
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


@pytest.mark.parametrize(
    ("run_subprocess_mock", "exp_res"),
    (
        (
            mock.Mock(return_value=(HOST_MODULES_STUB_GOOD, 0)),
            set(
                (
                    "kernel/lib/a.ko.xz",
                    "kernel/lib/b.ko.xz",
                    "kernel/lib/c.ko.xz",
                )
            ),
        ),
        (
            mock.Mock(return_value=("", 1)),
            None,
        ),
        (
            mock.Mock(side_effect=subprocess.CalledProcessError(returncode=1, cmd="")),
            None,
        ),
    ),
)
def test_get_installed_kmods(tmpdir, monkeypatch, caplog, run_subprocess_mock, exp_res):
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    if exp_res:
        assert exp_res == get_installed_kmods()
    else:
        with pytest.raises(SystemExit):
            get_installed_kmods()
        assert "Can't get list of kernel modules." in caplog.records[-1].message


@pytest.mark.parametrize(
    ("repoquery_f_stub", "repoquery_l_stub", "exception"),
    (
        (REPOQUERY_F_STUB_GOOD, REPOQUERY_L_STUB_GOOD, None),
        (REPOQUERY_F_STUB_BAD, REPOQUERY_L_STUB_GOOD, SystemExit),
    ),
)
def test_get_rhel_supported_kmods(
    monkeypatch,
    pretend_centos8,
    repoquery_f_stub,
    repoquery_l_stub,
    exception,
):
    run_subprocess_mock = mock.Mock(
        side_effect=_run_subprocess_side_effect(
            (
                ("repoquery", " -f "),
                (repoquery_f_stub, 0),
            ),
            (
                ("repoquery", " -l "),
                (repoquery_l_stub, 0),
            ),
        )
    )
    monkeypatch.setattr(
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    if exception:
        with pytest.raises(exception):
            get_rhel_supported_kmods()
    else:
        res = get_rhel_supported_kmods()
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
    ("pkgs", "exp_res", "exception"),
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
            None,
        ),
        (
            (
                "kmod-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",),
            None,
        ),
        (
            (
                "not-expected-core-0:4.18.0-240.10.1.el8_3.x86_64",
                "kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kmod-core-0:4.18.0-240.15.1.el8_3.x86_64",),
            None,
        ),
        (
            (
                "kernel-core-0:4.18.0-240.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",),
            None,
        ),
        (
            (
                "kernel-core-0:4.18.0-240.15.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",),
            None,
        ),
        (
            (
                "kernel-core-0:4.18.0-240.16.beta5.1.el8_3.x86_64",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            ("kernel-core-0:4.18.0-240.16.beta5.1.el8_3.x86_64",),
            None,
        ),
        (("kernel_bad_package:111111",), (), SystemExit),
        (
            (
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
                "kernel_bad_package:111111",
                "kernel-core-0:4.18.0-240.15.1.el8_3.x86_64",
            ),
            (),
            SystemExit,
        ),
    ),
)
def test_get_most_recent_unique_kernel_pkgs(pkgs, exp_res, exception):
    if not exception:
        most_recent_pkgs = tuple(get_most_recent_unique_kernel_pkgs(pkgs))
        assert exp_res == most_recent_pkgs
    else:
        with pytest.raises(exception):
            tuple(get_most_recent_unique_kernel_pkgs(pkgs))


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
        checks,
        "run_subprocess",
        value=run_subprocess_mock,
    )
    if expected_exception:
        with pytest.raises(expected_exception):
            check_tainted_kmods()
    else:
        check_tainted_kmods()


@pytest.mark.parametrize(
    # i.e. _bad_kernel_version...
    ("any_of_the_subchecks_is_true",),
    (
        (True,),
        (False,),
    ),
)
def test_check_rhel_compatible_kernel_is_used(
    any_of_the_subchecks_is_true,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        checks,
        "_bad_kernel_version",
        value=mock.Mock(return_value=any_of_the_subchecks_is_true),
    )
    monkeypatch.setattr(
        checks,
        "_bad_kernel_substring",
        value=mock.Mock(return_value=False),
    )
    monkeypatch.setattr(
        checks,
        "_bad_kernel_package_signature",
        value=mock.Mock(return_value=False),
    )
    if any_of_the_subchecks_is_true:
        with pytest.raises(SystemExit):
            check_rhel_compatible_kernel_is_used()
    else:
        check_rhel_compatible_kernel_is_used()
        assert "Kernel is compatible" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("kernel_release", "major_ver", "exp_return"),
    (
        ("5.11.0-7614-generic", None, True),
        ("3.10.0-1160.24.1.el7.x86_64", 7, False),
        ("3.10.0-1160.24.1.el7.x86_64", 6, True),
        ("5.4.17-2102.200.13.el8uek.x86_64", 8, True),
        ("4.18.0-240.22.1.el8_3.x86_64", 8, False),
    ),
)
def test_bad_kernel_version(kernel_release, major_ver, exp_return, monkeypatch):
    Version = namedtuple("Version", ("major", "minor"))
    monkeypatch.setattr(
        checks.system_info,
        "version",
        value=Version(major=major_ver, minor=0),
    )
    assert _bad_kernel_version(kernel_release) == exp_return


@pytest.mark.parametrize(
    ("kernel_release", "exp_return"),
    (
        ("3.10.0-1160.24.1.el7.x86_64", False),
        ("5.4.17-2102.200.13.el8uek.x86_64", True),
        ("3.10.0-514.2.2.rt56.424.el7.x86_64", True),
    ),
)
def test_bad_kernel_substring(kernel_release, exp_return, monkeypatch):
    assert _bad_kernel_substring(kernel_release) == exp_return


@pytest.mark.parametrize(
    ("kernel_release", "kernel_pkg", "kernel_pkg_fingerprint", "exp_return"),
    (
        (
            "4.18.0-240.22.1.el8_3.x86_64",
            "kernel-core",
            "05b555b38483c65d",
            False,
        ),
        (
            "4.18.0-240.22.1.el8_3.x86_64",
            "kernel-core",
            "somebadsig",
            True,
        ),
    ),
)
def test_bad_kernel_fingerprint(
    kernel_release,
    kernel_pkg,
    kernel_pkg_fingerprint,
    exp_return,
    monkeypatch,
    pretend_centos8,
):
    run_subprocess_mocked = mock.Mock(spec=run_subprocess, return_value=(kernel_pkg, ""))
    get_pkg_fingerprint_mocked = mock.Mock(spec=get_pkg_fingerprint, return_value=kernel_pkg_fingerprint)
    monkeypatch.setattr(checks, "run_subprocess", run_subprocess_mocked)
    monkeypatch.setattr(
        checks,
        "get_installed_pkg_objects",
        mock.Mock(return_value=[kernel_pkg]),
    )
    monkeypatch.setattr(checks, "get_pkg_fingerprint", get_pkg_fingerprint_mocked)
    assert _bad_kernel_package_signature(kernel_release) == exp_return


class TestUEFIChecks(unittest.TestCase):
    @unit_tests.mock(os.path, "exists", lambda x: x == "/sys/firmware/efi")
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    def test_check_uefi_efi_detected(self):
        self.assertRaises(SystemExit, checks.check_uefi)
        self.assertEqual(len(checks.logger.critical_msgs), 1)
        self.assertTrue("Conversion of UEFI systems is currently not supported" in checks.logger.critical_msgs[0])
        if checks.logger.debug_msgs:
            self.assertFalse("BIOS system detected." in checks.logger.info_msgs[0])

    @unit_tests.mock(os.path, "exists", lambda x: not x == "/sys/firmware/efi")
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    def test_check_uefi_bios_detected(self):
        checks.check_uefi()
        self.assertFalse(checks.logger.critical_msgs)
        self.assertTrue("BIOS system detected." in checks.logger.info_msgs[0])


class TestReadOnlyMountsChecks(unittest.TestCase):
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    @unit_tests.mock(
        checks,
        "get_file_content",
        GetFileContentMocked(
            data=[
                "sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "mnt /mnt sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
            ]
        ),
    )
    def test_mounted_are_readwrite(self):
        checks.check_readonly_mounts()
        self.assertEqual(len(checks.logger.critical_msgs), 0)
        self.assertEqual(len(checks.logger.debug_msgs), 2)
        self.assertTrue("/mnt mount point is not read-only." in checks.logger.debug_msgs)
        self.assertTrue("/sys mount point is not read-only." in checks.logger.debug_msgs)

    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    @unit_tests.mock(
        checks,
        "get_file_content",
        GetFileContentMocked(
            data=[
                "sysfs /sys sysfs rw,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "mnt /mnt sysfs ro,seclabel,nosuid,nodev,noexec,relatime 0 0",
                "cgroup /sys/fs/cgroup/cpuset cgroup rw,seclabel,nosuid,nodev,noexec,relatime,cpuset 0 0",
            ]
        ),
    )
    def test_mounted_are_readonly(self):
        self.assertRaises(SystemExit, checks.check_readonly_mounts)
        self.assertEqual(len(checks.logger.critical_msgs), 1)
        self.assertTrue(
            "Stopping conversion due to read-only mount to /mnt directory" in checks.logger.critical_msgs[0]
        )
        self.assertTrue(
            "Stopping conversion due to read-only mount to /sys directory" not in checks.logger.critical_msgs[0]
        )
        self.assertTrue("/sys mount point is not read-only." in checks.logger.debug_msgs[0])

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

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(checks, "call_yum_cmd", CallYumCmdMocked(ret_code=0, ret_string="Abcdef"))
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "disable_submgr", True)
    def test_custom_repos_are_valid(self):
        checks.check_custom_repos_are_valid()
        self.assertEqual(len(checks.logger.info_msgs), 1)
        self.assertEqual(len(checks.logger.debug_msgs), 1)
        self.assertTrue(
            "The repositories passed through the --enablerepo option are all accessible." in checks.logger.info_msgs
        )

    @unit_tests.mock(system_info, "version", namedtuple("Version", ["major", "minor"])(7, 0))
    @unit_tests.mock(checks, "call_yum_cmd", CallYumCmdMocked(ret_code=1, ret_string="Abcdef"))
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "disable_submgr", True)
    def test_custom_repos_are_invalid(self):
        self.assertRaises(SystemExit, checks.check_custom_repos_are_valid)
        self.assertEqual(len(checks.logger.critical_msgs), 1)
        self.assertEqual(len(checks.logger.info_msgs), 0)
        self.assertTrue("Unable to access the repositories passed through " in checks.logger.critical_msgs[0])
