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
from convert2rhel.actions.system_checks.rhel_compatible_kernel import (
    BAD_KERNEL_RELEASE_SUBSTRINGS,
    COMPATIBLE_KERNELS_VERS,
    KernelIncompatibleError,
)
from convert2rhel.unit_tests import RunSubprocessMocked, create_pkg_information
from convert2rhel.unit_tests.conftest import centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def rhel_compatible_kernel_action():
    return rhel_compatible_kernel.RhelCompatibleKernel()


def test_check_rhel_compatible_kernel_failure(
    monkeypatch,
    rhel_compatible_kernel_action,
):
    monkeypatch.setattr(
        rhel_compatible_kernel,
        "_bad_kernel_version",
        value=mock.Mock(
            side_effect=KernelIncompatibleError("UNEXPECTED_VERSION", "Bad kernel version", {"fake_data": "fake"})
        ),
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
    monkeypatch.setattr(
        rhel_compatible_kernel.system_info,
        "name",
        value="Kernel-core",
    )
    rhel_compatible_kernel_action.run()
    unit_tests.assert_actions_result(
        rhel_compatible_kernel_action,
        level="ERROR",
        id="UNEXPECTED_VERSION",
        title="Incompatible booted kernel version",
        description="Please refer to the diagnosis for further information",
        diagnosis="The booted kernel version is incompatible with the standard RHEL kernel",
        remediations=(
            "To proceed with the conversion, boot into a kernel that is available in the {0} {1} base repository"
            " by executing the following steps:\n\n"
            "1. Ensure that the {0} {1} base repository is enabled\n"
            "2. Run: yum install kernel\n"
            "3. (optional) Run: grubby --set-default "
            '/boot/vmlinuz-`rpm -q --qf "%{{BUILDTIME}}\\t%{{EVR}}.%{{ARCH}}\\n" kernel | sort -nr | head -1 | cut -f2`\n'
            "4. Reboot the machine and if step 3 was not applied choose the kernel"
            " installed in step 2 manually".format(
                rhel_compatible_kernel.system_info.name, rhel_compatible_kernel.system_info.version.major
            )
        ),
    )


def test_rhel_compatible_kernel_success(monkeypatch, caplog, rhel_compatible_kernel_action):
    monkeypatch.setattr(
        rhel_compatible_kernel,
        "_bad_kernel_version",
        value=mock.Mock(return_value=False),
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
    monkeypatch.setattr(
        rhel_compatible_kernel.system_info,
        "name",
        value="Kernel-core",
    )
    rhel_compatible_kernel_action.run()

    assert "is compatible with RHEL" in caplog.records[-1].message


@pytest.mark.parametrize(
    ("kernel_release", "major_ver", "exp_return"),
    (
        ("3.10.0-1160.24.1.el7.x86_64", 7, False),
        ("4.18.0-240.22.1.el8_3.x86_64", 8, False),
    ),
)
def test_bad_kernel_version_success(kernel_release, major_ver, exp_return, monkeypatch):
    Version = namedtuple("Version", ("major", "minor"))
    monkeypatch.setattr(
        rhel_compatible_kernel.system_info,
        "version",
        value=Version(major=major_ver, minor=0),
    )
    assert rhel_compatible_kernel._bad_kernel_version(kernel_release) == exp_return


@pytest.mark.parametrize(
    ("kernel_release", "major_ver", "error_id", "template", "variables"),
    (
        (
            "5.11.0-7614-generic",
            None,
            "UNEXPECTED_VERSION",
            "Unexpected OS major version. Expected: {compatible_version}",
            {"compatible_version": COMPATIBLE_KERNELS_VERS.keys()},
        ),
        (
            "5.4.17-2102.200.13.el8uek.x86_64",
            8,
            "INCOMPATIBLE_VERSION",
            "Booted kernel version '{kernel_version}' does not correspond to the version "
            "'{compatible_version}' available in RHEL {rhel_major_version}",
            {"kernel_version": "5.4.17", "compatible_version": COMPATIBLE_KERNELS_VERS[8], "rhel_major_version": 8},
        ),
    ),
)
def test_bad_kernel_version_invalid_version(kernel_release, major_ver, error_id, template, variables, monkeypatch):
    Version = namedtuple("Version", ("major", "minor"))
    monkeypatch.setattr(
        rhel_compatible_kernel.system_info,
        "version",
        value=Version(major=major_ver, minor=0),
    )
    with pytest.raises(KernelIncompatibleError) as excinfo:
        rhel_compatible_kernel._bad_kernel_version(kernel_release)
    assert excinfo.value.error_id == error_id
    assert excinfo.value.template == template
    assert excinfo.value.variables == variables


@pytest.mark.parametrize(
    ("kernel_release", "exp_return"),
    (
        ("3.10.0-1160.24.1.el7.x86_64", False),
        ("5.04.0-1240.41.0.el8.x86_64", False),
    ),
)
def test_bad_kernel_substring_success(kernel_release, exp_return):
    assert rhel_compatible_kernel._bad_kernel_substring(kernel_release) == exp_return


@pytest.mark.parametrize(
    ("kernel_release", "error_id", "template", "variables"),
    (
        (
            "5.4.17-2102.200.13.el8uek.x86_64",
            "INVALID_PACKAGE_SUBSTRING",
            "The booted kernel '{kernel_release}' contains one of the disallowed "
            "substrings: {bad_kernel_release_substrings}",
            {
                "kernel_release": "5.4.17-2102.200.13.el8uek.x86_64",
                "bad_kernel_release_substrings": BAD_KERNEL_RELEASE_SUBSTRINGS,
            },
        ),
        (
            "3.10.0-514.2.2.rt56.424.el7.x86_64",
            "INVALID_PACKAGE_SUBSTRING",
            "The booted kernel '{kernel_release}' contains one of the disallowed "
            "substrings: {bad_kernel_release_substrings}",
            {
                "kernel_release": "3.10.0-514.2.2.rt56.424.el7.x86_64",
                "bad_kernel_release_substrings": BAD_KERNEL_RELEASE_SUBSTRINGS,
            },
        ),
    ),
)
def test_bad_kernel_substring_invalid_substring(kernel_release, error_id, template, variables, monkeypatch):
    with pytest.raises(KernelIncompatibleError) as excinfo:
        rhel_compatible_kernel._bad_kernel_substring(kernel_release)
    assert excinfo.value.error_id == error_id
    assert excinfo.value.template == template
    assert excinfo.value.variables == variables


@pytest.mark.parametrize(
    ("kernel_release", "kernel_pkg", "kernel_pkg_information", "exp_return"),
    (
        (
            "4.18.0-240.22.1.el8_3.x86_64",
            "4.18.0&240.22.1.el8_3&x86_64&kernel-core",
            create_pkg_information(
                name="kernel-core",
                epoch="0",
                version="4.18.0",
                release="240.22.1.el8_3",
                arch="x86_64",
                key_id="05b555b38483c65d",
            ),
            False,
        ),
    ),
)
@centos8
def test_bad_kernel_package_signature_success(
    kernel_release,
    kernel_pkg,
    kernel_pkg_information,
    exp_return,
    monkeypatch,
    pretend_os,
):
    run_subprocess_mocked = RunSubprocessMocked(return_string=kernel_pkg)
    monkeypatch.setattr(rhel_compatible_kernel, "run_subprocess", run_subprocess_mocked)
    get_installed_pkg_information_mocked = mock.Mock(return_value=[kernel_pkg_information])
    monkeypatch.setattr(rhel_compatible_kernel, "get_installed_pkg_information", get_installed_pkg_information_mocked)
    assert rhel_compatible_kernel._bad_kernel_package_signature(kernel_release) == exp_return
    run_subprocess_mocked.assert_called_with(
        ["rpm", "-qf", "--qf", "%{NEVRA}", "/boot/vmlinuz-{}".format(kernel_release)],
        print_output=False,
    )


@pytest.mark.parametrize(
    (
        "kernel_release",
        "kernel_pkg",
        "kernel_pkg_information",
        "error_id",
        "template",
        "variables",
    ),
    (
        (
            "4.18.0-240.22.1.el8_3.x86_64",
            "4.18.0&240.22.1.el8_3&x86_64&kernel-core",
            create_pkg_information(
                name="kernel-core",
                epoch="0",
                version="4.18.0",
                release="240.22.1.el8_3",
                arch="x86_64",
                key_id="somebadsig",
            ),
            "INVALID_KERNEL_PACKAGE_SIGNATURE",
            "Custom kernel detected. The booted kernel needs to be signed by {os_vendor}.",
            {"os_vendor": "CentOS"},
        ),
    ),
)
@centos8
def test_bad_kernel_package_signature_invalid_signature(
    kernel_release,
    kernel_pkg,
    kernel_pkg_information,
    error_id,
    template,
    variables,
    monkeypatch,
    pretend_os,
):
    run_subprocess_mocked = RunSubprocessMocked(return_string=kernel_pkg)
    monkeypatch.setattr(rhel_compatible_kernel, "run_subprocess", run_subprocess_mocked)
    get_installed_pkg_information_mocked = mock.Mock(return_value=[kernel_pkg_information])
    monkeypatch.setattr(rhel_compatible_kernel, "get_installed_pkg_information", get_installed_pkg_information_mocked)

    with pytest.raises(KernelIncompatibleError) as excinfo:
        rhel_compatible_kernel._bad_kernel_package_signature(kernel_release)
    assert excinfo.value.error_id == error_id
    assert excinfo.value.template == template
    assert excinfo.value.variables == variables
    run_subprocess_mocked.assert_called_with(
        ["rpm", "-qf", "--qf", "%{NEVRA}", "/boot/vmlinuz-{}".format(kernel_release)],
        print_output=False,
    )


@pytest.mark.parametrize(
    ("error_id", "template", "variables"),
    (
        (
            "UNSIGNED_PACKAGE",
            "The booted kernel {vmlinuz_path} is not owned by any installed package."
            " It needs to be owned by a package signed by {os_vendor}.",
            {"vmlinuz_path": "/boot/vmlinuz-4.18.0-240.22.1.el8_3.x86_64", "os_vendor": "CentOS"},
        ),
    ),
)
@centos8
def test_kernel_not_installed(pretend_os, error_id, template, variables, monkeypatch):
    run_subprocess_mocked = RunSubprocessMocked(return_value=(" ", 1))
    monkeypatch.setattr(rhel_compatible_kernel, "run_subprocess", run_subprocess_mocked)

    with pytest.raises(KernelIncompatibleError) as excinfo:
        rhel_compatible_kernel._bad_kernel_package_signature("4.18.0-240.22.1.el8_3.x86_64")
    assert excinfo.value.error_id == error_id
    assert excinfo.value.template == template
    assert excinfo.value.variables == variables
