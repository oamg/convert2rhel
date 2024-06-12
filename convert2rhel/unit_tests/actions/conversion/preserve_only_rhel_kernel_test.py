# Copyright(C) 2024 Red Hat, Inc.
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
import six

from convert2rhel import exceptions, pkghandler, unit_tests, utils
from convert2rhel.actions import STATUS_CODE
from convert2rhel.actions.conversion import preserve_only_rhel_kernel
from convert2rhel.unit_tests import (
    GetInstalledPkgsByFingerprintMocked,
    GetInstalledPkgsWDifferentFingerprintMocked,
    RunSubprocessMocked,
)
from convert2rhel.unit_tests.conftest import all_systems, centos7, centos8


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def install_rhel_kernel_instance():
    return preserve_only_rhel_kernel.InstallRhelKernel()


@pytest.fixture
def verify_rhel_kernel_installed_instance():
    return preserve_only_rhel_kernel.VerifyRhelKernelInstalled()


@pytest.fixture
def fix_invalid_grub2_entries_instance():
    return preserve_only_rhel_kernel.FixInvalidGrub2Entries()


@pytest.fixture
def fix_default_kernel_instance():
    return preserve_only_rhel_kernel.FixDefaultKernel()


@pytest.fixture
def kernel_packages_install_instance():
    return preserve_only_rhel_kernel.KernelPkgsInstall()


@pytest.mark.parametrize(
    (
        "subprocess_output",
        "is_only_rhel_kernel",
        "expected",
    ),
    (
        ("Package kernel-3.10.0-1127.19.1.el7.x86_64 already installed and latest version", True, False),
        ("Package kernel-3.10.0-1127.19.1.el7.x86_64 already installed and latest version", False, True),
        ("Installed:\nkernel", False, False),
    ),
    ids=(
        "Kernels collide and installed is already RHEL. Do not update.",
        "Kernels collide and installed is not RHEL and older. Update.",
        "Kernels do not collide. Install RHEL kernel and do not update.",
    ),
)
@centos7
def test_install_rhel_kernel(
    subprocess_output, is_only_rhel_kernel, expected, pretend_os, install_rhel_kernel_instance, monkeypatch
):
    update_rhel_kernel_mock = mock.Mock()

    monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output))
    monkeypatch.setattr(pkghandler, "handle_no_newer_rhel_kernel_available", mock.Mock())
    monkeypatch.setattr(pkghandler, "update_rhel_kernel", value=update_rhel_kernel_mock)

    if is_only_rhel_kernel:
        pkg_selection = "empty"
    else:
        pkg_selection = "kernels"

    monkeypatch.setattr(
        pkghandler,
        "get_installed_pkgs_w_different_fingerprint",
        GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection=pkg_selection),
    )
    install_rhel_kernel_instance.run()
    if expected:
        assert update_rhel_kernel_mock.assert_called_once()
