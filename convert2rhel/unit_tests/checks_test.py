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

import pytest

from convert2rhel import checks, unit_tests
from convert2rhel.checks import (
    _get_kmod_comparison_key,
    check_tainted_kmods,
    ensure_compatibility_of_kmods,
    get_installed_kmods,
    get_most_recent_unique_kernel_pkgs,
    get_rhel_supported_kmods,
    get_unsupported_kmods,
    perform_pre_checks,
    perform_pre_ponr_checks,
)
from convert2rhel.unit_tests import GetLoggerMocked
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

    perform_pre_checks()

    check_thirdparty_kmods_mock.assert_called_once()
    check_uefi_mock.assert_called_once()


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
    ),
    (
        (
            "/lib/modules/3.10.0-1160.6.1/kernel/drivers/input/ff-memless.ko.xz\n",
            "Kernel modules are compatible",
            "The following kernel modules are not supported in RHEL",
        ),
        (
            "/lib/modules/3.10.0-1160.6.1/kernel/drivers/input/other.ko.xz\n",
            "The following kernel modules are not supported in RHEL",
            None,
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
):
    get_unsupported_kmods_mocked = mock.Mock(
        wraps=checks.get_unsupported_kmods
    )
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
        assert msg_in_logs in caplog.records[0].message
    if msg_not_in_logs:
        assert all(
            msg_not_in_logs not in record.message for record in caplog.records
        )


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
            mock.Mock(
                side_effect=subprocess.CalledProcessError(returncode=1, cmd="")
            ),
            None,
        ),
    ),
)
def test_get_installed_kmods(
    tmpdir, monkeypatch, caplog, run_subprocess_mock, exp_res
):
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
        assert (
            "Can't get list of kernel modules." in caplog.records[-1].message
        )


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


class TestUEFIChecks(unittest.TestCase):
    @unit_tests.mock(os.path, "exists", lambda x: x == "/sys/firmware/efi")
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    def test_check_uefi_efi_detected(self):
        self.assertRaises(SystemExit, checks.check_uefi)
        self.assertEqual(len(checks.logger.critical_msgs), 1)
        self.assertTrue(
            "Conversion of UEFI systems is currently not supported"
            in checks.logger.critical_msgs[0]
        )
        if checks.logger.debug_msgs:
            self.assertFalse(
                "Converting BIOS system" in checks.logger.debug_msgs[0]
            )

    @unit_tests.mock(os.path, "exists", lambda x: not x == "/sys/firmware/efi")
    @unit_tests.mock(checks, "logger", GetLoggerMocked())
    def test_check_uefi_bios_detected(self):
        checks.check_uefi()
        self.assertFalse(checks.logger.critical_msgs)
        self.assertTrue(
            "Converting BIOS system" in checks.logger.debug_msgs[0]
        )
