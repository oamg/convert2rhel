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

from collections import namedtuple

import pytest
import six

from convert2rhel import unit_tests
from convert2rhel.actions.system_checks import rhel_compatible_kernel
from convert2rhel.unit_tests.conftest import centos8
from convert2rhel.utils import run_subprocess


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def rhel_compatible_kernel_action():
    return rhel_compatible_kernel.RhelCompatibleKernel()


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
    rhel_compatible_kernel_action,
):
    monkeypatch.setattr(
        rhel_compatible_kernel,
        "_bad_kernel_version",
        value=mock.Mock(return_value=any_of_the_subchecks_is_true),
    )
    monkeypatch.setattr(
        rhel_compatible_kernel,
        "_bad_kernel_substring",
        value=mock.Mock(return_value=False),
    )
    monkeypatch.setattr(
        rhel_compatible_kernel,
        "_bad_kernel_package_signature",
        value=mock.Mock(return_value=False),
    )
    Version = namedtuple("Version", ("major", "minor"))
    monkeypatch.setattr(
        rhel_compatible_kernel.system_info,
        "version",
        value=Version(major=1, minor=0),
    )
    rhel_compatible_kernel_action.run()
    if any_of_the_subchecks_is_true:
        unit_tests.assert_actions_result(
            rhel_compatible_kernel_action,
            status="ERROR",
            error_id="BOOTED_KERNEL_INCOMPATIBLE",
            message=(
                "The booted kernel version is incompatible with the standard RHEL kernel. "
                "To proceed with the conversion, boot into a kernel that is available in the {0} {1} base repository"
                " by executing the following steps:\n\n"
                "1. Ensure that the {0} {1} base repository is enabled\n"
                "2. Run: yum install kernel\n"
                "3. (optional) Run: grubby --set-default "
                '/boot/vmlinuz-`rpm -q --qf "%{{BUILDTIME}}\\t%{{EVR}}.%{{ARCH}}\\n" kernel | sort -nr | head -1 | cut -f2`\n'
                "4. Reboot the machine and if step 3 was not applied choose the kernel"
                " installed in step 2 manually".format(
                    rhel_compatible_kernel.system_info.name,
                    rhel_compatible_kernel.system_info.version.major,
                )
            ),
        )
    else:
        assert "is compatible with RHEL" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("kernel_release", "major_ver", "exp_return"),
    (
        ("5.11.0-7614-generic", None, True),
        ("3.10.0-1160.24.1.el7.x86_64", 7, False),
        ("5.4.17-2102.200.13.el8uek.x86_64", 8, True),
        ("4.18.0-240.22.1.el8_3.x86_64", 8, False),
    ),
)
def test_bad_kernel_version(kernel_release, major_ver, exp_return, monkeypatch):
    Version = namedtuple("Version", ("major", "minor"))
    monkeypatch.setattr(
        rhel_compatible_kernel.system_info,
        "version",
        value=Version(major=major_ver, minor=0),
    )
    assert rhel_compatible_kernel._bad_kernel_version(kernel_release) == exp_return


@pytest.mark.parametrize(
    ("kernel_release", "exp_return"),
    (
        ("3.10.0-1160.24.1.el7.x86_64", False),
        ("5.4.17-2102.200.13.el8uek.x86_64", True),
        ("3.10.0-514.2.2.rt56.424.el7.x86_64", True),
    ),
)
def test_bad_kernel_substring(kernel_release, exp_return, monkeypatch):
    assert rhel_compatible_kernel._bad_kernel_substring(kernel_release) == exp_return


@pytest.mark.parametrize(
    ("kernel_release", "kernel_pkg", "kernel_pkg_fingerprint", "get_installed_pkg_objects", "exp_return"),
    (
        (
            "4.18.0-240.22.1.el8_3.x86_64",
            "4.18.0&240.22.1.el8_3&x86_64&kernel-core",
            "05b555b38483c65d",
            "yajl.x86_64",
            False,
        ),
        (
            "4.18.0-240.22.1.el8_3.x86_64",
            "4.18.0&240.22.1.el8_3&x86_64&kernel-core",
            "somebadsig",
            "somepkgobj",
            True,
        ),
    ),
)
@centos8
def test_bad_kernel_package_signature(
    kernel_release,
    kernel_pkg,
    kernel_pkg_fingerprint,
    get_installed_pkg_objects,
    exp_return,
    monkeypatch,
    pretend_os,
):
    run_subprocess_mocked = mock.Mock(spec=run_subprocess, return_value=(kernel_pkg, 0))
    get_pkg_fingerprint_mocked = mock.Mock(
        spec=rhel_compatible_kernel.get_pkg_fingerprint, return_value=kernel_pkg_fingerprint
    )
    monkeypatch.setattr(rhel_compatible_kernel, "run_subprocess", run_subprocess_mocked)
    get_installed_pkg_objects_mocked = mock.Mock(
        spec=rhel_compatible_kernel.get_installed_pkg_objects, return_value=[kernel_pkg]
    )
    monkeypatch.setattr(
        rhel_compatible_kernel,
        "get_installed_pkg_objects",
        get_installed_pkg_objects_mocked,
    )
    monkeypatch.setattr(rhel_compatible_kernel, "get_pkg_fingerprint", get_pkg_fingerprint_mocked)
    assert rhel_compatible_kernel._bad_kernel_package_signature(kernel_release) == exp_return
    run_subprocess_mocked.assert_called_with(
        ["rpm", "-qf", "--qf", "%{VERSION}&%{RELEASE}&%{ARCH}&%{NAME}", "/boot/vmlinuz-%s" % kernel_release],
        print_output=False,
    )


@centos8
def test_kernel_not_installed(pretend_os, caplog, monkeypatch):
    run_subprocess_mocked = mock.Mock(spec=run_subprocess, return_value=(" ", 1))
    monkeypatch.setattr(rhel_compatible_kernel, "run_subprocess", run_subprocess_mocked)
    assert rhel_compatible_kernel._bad_kernel_package_signature("4.18.0-240.22.1.el8_3.x86_64")
    log_message = (
        "The booted kernel /boot/vmlinuz-4.18.0-240.22.1.el8_3.x86_64 is not owned by any installed package."
        " It needs to be owned by a package signed by CentOS."
    )
    assert log_message in caplog.text
