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
import glob
import os
import re

import pytest
import six

from convert2rhel import actions, pkghandler, pkgmanager, unit_tests, utils
from convert2rhel.actions.conversion import preserve_only_rhel_kernel
from convert2rhel.systeminfo import Version, system_info
from convert2rhel.unit_tests import (
    CallYumCmdMocked,
    FormatPkgInfoMocked,
    GetInstalledPkgsByFingerprintMocked,
    GetInstalledPkgsWDifferentFingerprintMocked,
    RemovePkgsMocked,
    RunSubprocessMocked,
    StoreContentToFileMocked,
    create_pkg_information,
)
from convert2rhel.unit_tests.conftest import centos7, centos8


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


class TestInstallRhelKernel:
    @pytest.mark.parametrize(
        (
            "subprocess_output",
            "pkgs_w_diff_fingerprint",
            "no_newer_kernel_call",
            "update_kernel_call",
            "action_message",
            "action_result",
        ),
        (
            (
                # Info about installed kernel from yum contains the same version as is listed in the different fingerprint pkgs
                # The latest installed kernel is from CentOS
                "Package kernel-4.18.0-193.el8.x86_64 is already installed.",
                [
                    create_pkg_information(
                        name="kernel",
                        version="4.18.0",
                        release="193.el8",
                        arch="x86_64",
                        packager="CentOS",
                    ),
                    create_pkg_information(
                        name="kernel",
                        version="4.18.0",
                        release="183.el8",
                        arch="x86_64",
                        packager="CentOS",
                    ),
                ],
                1,
                1,
                set(
                    (
                        actions.ActionMessage(
                            level="INFO",
                            id="CONFLICT_OF_KERNELS",
                            title="Conflict of installed kernel versions",
                            description="Conflict of kernels: The running kernel has the same version as the latest RHEL kernel. "
                            "The kernel package could not be replaced during the main transaction. "
                            "We will try to install a lower version of the package, "
                            "remove the conflicting kernel and then update to the latest security patched version.",
                        ),
                    ),
                ),
                actions.ActionResult(level="SUCCESS", id="SUCCESS"),
            ),
            (
                # Output from yum contains different version than is listed in different fingerprint
                # Rhel kernel already installed with centos kernels
                "Package kernel-4.18.0-205.el8.x86_64 is already installed.",
                [
                    create_pkg_information(
                        name="kernel",
                        version="4.18.0",
                        release="193.el8",
                        arch="x86_64",
                        packager="CentOS",
                    ),
                    create_pkg_information(
                        name="kernel",
                        version="4.18.0",
                        release="183.el8",
                        arch="x86_64",
                        packager="CentOS",
                    ),
                ],
                0,
                0,
                set(()),
                actions.ActionResult(level="SUCCESS", id="SUCCESS"),
            ),
            (
                # Only rhel kernel already installed
                "Package kernel-4.18.0-205.el8.x86_64 is already installed.",
                [],
                0,
                0,
                set(()),
                actions.ActionResult(level="SUCCESS", id="SUCCESS"),
            ),
            (
                # Output from yum contains different version than is listed in different fingerprint
                # Rhel kernel already installed in older versin than centos kernel
                "Package kernel-4.18.0-183.el8.x86_64 is already installed.",
                [
                    create_pkg_information(
                        name="kernel",
                        version="4.18.0",
                        release="193.el8",
                        arch="x86_64",
                        packager="CentOS",
                    ),
                ],
                1,
                1,
                set(()),
                actions.ActionResult(level="SUCCESS", id="SUCCESS"),
            ),
        ),
    )
    @centos8
    def test_install_rhel_kernel(
        self,
        monkeypatch,
        subprocess_output,
        pkgs_w_diff_fingerprint,
        install_rhel_kernel_instance,
        no_newer_kernel_call,
        update_kernel_call,
        pretend_os,
        action_message,
        action_result,
    ):
        """Test the logic of kernel installation&update"""
        handle_no_newer_rhel_kernel_available = mock.Mock()
        update_rhel_kernel = mock.Mock()

        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output, return_code=0)
        )
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_w_different_fingerprint",
            GetInstalledPkgsWDifferentFingerprintMocked(return_value=pkgs_w_diff_fingerprint),
        )
        monkeypatch.setattr(pkghandler, "handle_no_newer_rhel_kernel_available", handle_no_newer_rhel_kernel_available)
        monkeypatch.setattr(pkghandler, "update_rhel_kernel", update_rhel_kernel)

        install_rhel_kernel_instance.run()

        assert handle_no_newer_rhel_kernel_available.call_count == no_newer_kernel_call
        assert update_rhel_kernel.call_count == update_kernel_call
        assert action_message.issuperset(install_rhel_kernel_instance.messages)
        assert action_message.issubset(install_rhel_kernel_instance.messages)
        assert action_result == install_rhel_kernel_instance.result

    @pytest.mark.parametrize(
        ("subprocess_output", "subprocess_return", "action_message", "action_result"),
        (
            (
                "yum command failed",
                1,
                set(()),
                actions.ActionResult(
                    level="ERROR",
                    id="FAILED_TO_INSTALL_RHEL_KERNEL",
                    title="Failed to install RHEL kernel",
                    description="There was an error while attempting to install the RHEL kernel from yum.",
                    remediations="Please check that you can access the repositories that provide the RHEL kernel.",
                ),
            ),
        ),
    )
    @centos8
    def test_install_rhel_kernel_yum_fail(
        self,
        monkeypatch,
        subprocess_output,
        subprocess_return,
        action_message,
        action_result,
        install_rhel_kernel_instance,
        pretend_os,
    ):
        monkeypatch.setattr(
            utils, "run_subprocess", RunSubprocessMocked(return_string=subprocess_output, return_code=subprocess_return)
        )

        install_rhel_kernel_instance.run()

        assert action_message.issuperset(install_rhel_kernel_instance.messages)
        assert action_message.issubset(install_rhel_kernel_instance.messages)
        assert action_result == install_rhel_kernel_instance.result


class TestKernelPkgsInstall:
    @pytest.mark.parametrize(
        ("kernel_pkgs_to_install",),
        (
            (["example_pkg"],),
            ([],),
        ),
    )
    def test_kernel_pkgs_install(self, monkeypatch, kernel_packages_install_instance, kernel_pkgs_to_install):
        install_additional_rhel_kernel_pkgs_mock = mock.Mock()
        monkeypatch.setattr(
            preserve_only_rhel_kernel.KernelPkgsInstall,
            "install_additional_rhel_kernel_pkgs",
            value=install_additional_rhel_kernel_pkgs_mock,
        )
        monkeypatch.setattr(
            preserve_only_rhel_kernel.KernelPkgsInstall,
            "remove_non_rhel_kernels",
            mock.Mock(return_value=kernel_pkgs_to_install),
        )

        kernel_packages_install_instance.run()
        if kernel_pkgs_to_install:
            install_additional_rhel_kernel_pkgs_mock.assert_called_once()

    def test_remove_non_rhel_kernels(self, monkeypatch, kernel_packages_install_instance):
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_w_different_fingerprint",
            GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection="kernels"),
        )
        monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
        monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())

        removed_pkgs = kernel_packages_install_instance.remove_non_rhel_kernels()

        assert len(removed_pkgs) == 6
        assert [p.nevra.name for p in removed_pkgs] == [
            "kernel",
            "kernel-uek",
            "kernel-headers",
            "kernel-uek-headers",
            "kernel-firmware",
            "kernel-uek-firmware",
        ]

    def test_install_additional_rhel_kernel_pkgs(self, monkeypatch, kernel_packages_install_instance):
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_w_different_fingerprint",
            GetInstalledPkgsWDifferentFingerprintMocked(pkg_selection="kernels"),
        )
        monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
        monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())
        monkeypatch.setattr(pkgmanager, "call_yum_cmd", CallYumCmdMocked())

        removed_pkgs = kernel_packages_install_instance.remove_non_rhel_kernels()
        kernel_packages_install_instance.install_additional_rhel_kernel_pkgs(removed_pkgs)
        assert pkgmanager.call_yum_cmd.call_count == 2


class TestVerifyRHELKernelInstalled:
    def test_verify_rhel_kernel_installed(self, monkeypatch, verify_rhel_kernel_installed_instance):
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_by_fingerprint",
            GetInstalledPkgsByFingerprintMocked(return_value=[create_pkg_information(name="kernel")]),
        )
        verify_rhel_kernel_installed_instance.run()
        expected = set(
            (
                actions.ActionMessage(
                    level="INFO",
                    id="RHEL_KERNEL_INSTALL_VERIFIED",
                    title="RHEL kernel install verified",
                    description="The RHEL kernel has been verified to be on the system.",
                    diagnosis=None,
                    remediations=None,
                ),
            )
        )
        assert expected.issuperset(verify_rhel_kernel_installed_instance.messages)
        assert expected.issubset(verify_rhel_kernel_installed_instance.messages)

    def test_verify_rhel_kernel_installed_not_installed(self, monkeypatch, verify_rhel_kernel_installed_instance):
        monkeypatch.setattr(pkghandler, "get_installed_pkgs_by_fingerprint", mock.Mock(return_value=[]))

        verify_rhel_kernel_installed_instance.run()
        unit_tests.assert_actions_result(
            verify_rhel_kernel_installed_instance,
            level="ERROR",
            id="NO_RHEL_KERNEL_INSTALLED",
            title="No RHEL kernel installed",
            description="There is no RHEL kernel installed on the system.",
            remediations="Verify that the repository used for installing kernel contains RHEL packages.",
        )


class TestFixInvalidGrub2Entries:
    def test_fix_invalid_grub2_entries(self, caplog, monkeypatch, fix_invalid_grub2_entries_instance):
        monkeypatch.setattr(system_info, "version", Version(8, 0))
        monkeypatch.setattr(system_info, "arch", "x86_64")
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda x: "1b11755afe1341d7a86383ca4944c324\n",
        )
        monkeypatch.setattr(
            glob,
            "glob",
            lambda x: [
                "/boot/loader/entries/1b11755afe1341d7a86383ca4944c324-0-rescue.conf",
                "/boot/loader/entries/1b11755afe1341d7a86383ca4944c324-4.18.0-193.28.1.el8_2.x86_64.conf",
                "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-0-rescue.conf",
                "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-4.18.0-193.el8.x86_64.conf",
                "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-5.4.17-2011.7.4.el8uek.x86_64.conf",
            ],
        )
        monkeypatch.setattr(os, "remove", mock.Mock())
        monkeypatch.setattr(utils, "run_subprocess", RunSubprocessMocked())

        fix_invalid_grub2_entries_instance.run()

        assert os.remove.call_count == 3
        assert utils.run_subprocess.call_count == 2

    @centos8
    @pytest.mark.parametrize(
        ("return_code_1", "return_code_2", "expected"),
        (
            (
                1,
                0,
                set(
                    (
                        actions.ActionMessage(
                            level="WARNING",
                            id="UNABLE_TO_GET_GRUB2_BOOT_LOADER_ENTRY",
                            title="Unable to get the GRUB2 boot loader entry",
                            description="Couldn't get the default GRUB2 boot loader entry:\nbootloader",
                            diagnosis=None,
                            remediations=None,
                        ),
                    )
                ),
            ),
            (
                0,
                1,
                set(
                    (
                        actions.ActionMessage(
                            level="WARNING",
                            id="UNABLE_TO_SET_GRUB2_BOOT_LOADER_ENTRY",
                            title="Unable to set the GRUB2 boot loader entry",
                            description="Couldn't set the default GRUB2 boot loader entry:\nbootloader",
                            diagnosis=None,
                            remediations=None,
                        ),
                    )
                ),
            ),
        ),
    )
    def test_fix_invalid_grub2_entries_messages(
        self, monkeypatch, fix_invalid_grub2_entries_instance, return_code_1, return_code_2, expected, pretend_os
    ):
        monkeypatch.setattr(os, "remove", mock.Mock())
        monkeypatch.setattr(
            glob,
            "glob",
            lambda x: [
                "/boot/loader/entries/1b11755afe1341d7a86383ca4944c324-0-rescue.conf",
                "/boot/loader/entries/1b11755afe1341d7a86383ca4944c324-4.18.0-193.28.1.el8_2.x86_64.conf",
                "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-0-rescue.conf",
                "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-4.18.0-193.el8.x86_64.conf",
                "/boot/loader/entries/b5aebfb91bff486bb9d44ba85e4ae683-5.4.17-2011.7.4.el8uek.x86_64.conf",
            ],
        )
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda x: "1b11755afe1341d7a86383ca4944c324\n",
        )
        run_subprocess_mocked = RunSubprocessMocked(
            side_effect=unit_tests.run_subprocess_side_effect(
                (
                    (
                        "/usr/sbin/grubby",
                        "--default-kernel",
                    ),
                    (
                        "bootloader",
                        return_code_1,
                    ),
                ),
                (
                    (
                        "/usr/sbin/grubby",
                        "--set-default",
                        "bootloader",
                    ),
                    (
                        "bootloader",
                        return_code_2,
                    ),
                ),
            ),
        )

        monkeypatch.setattr(
            utils,
            "run_subprocess",
            value=run_subprocess_mocked,
        )

        fix_invalid_grub2_entries_instance.run()
        assert expected.issuperset(fix_invalid_grub2_entries_instance.messages)
        assert expected.issubset(fix_invalid_grub2_entries_instance.messages)

    @pytest.mark.parametrize(
        ("version", "expected"),
        (
            (Version(7, 9), False),
            (Version(8, 9), True),
        ),
    )
    def test_fix_invalid_grub2_entries_execution(
        self, monkeypatch, fix_invalid_grub2_entries_instance, caplog, version, expected
    ):

        monkeypatch.setattr(system_info, "version", version)
        run_subprocess_mocked = RunSubprocessMocked(
            side_effect=unit_tests.run_subprocess_side_effect(
                (
                    (
                        "/usr/sbin/grubby",
                        "--default-kernel",
                    ),
                    (
                        "bootloader",
                        0,
                    ),
                ),
                (
                    (
                        "/usr/sbin/grubby",
                        "--set-default",
                        "bootloader",
                    ),
                    (
                        "bootloader",
                        0,
                    ),
                ),
            ),
        )

        monkeypatch.setattr(
            utils,
            "run_subprocess",
            value=run_subprocess_mocked,
        )
        fix_invalid_grub2_entries_instance.run()
        if expected:
            assert "Fixing GRUB boot loader" in caplog.text
        else:
            assert "Fixing GRUB boot loader" not in caplog.text


class TestFixDefaultKernel:
    @pytest.mark.parametrize(
        ("system_name", "version", "old_kernel", "new_kernel", "not_default_kernels"),
        (
            (
                "Oracle Linux Server release 7.9",
                Version(7, 9),
                "kernel-uek",
                "kernel",
                ("kernel-uek", "kernel-core"),
            ),
            (
                "Oracle Linux Server release 8.1",
                Version(8, 1),
                "kernel-uek",
                "kernel-core",
                ("kernel-uek", "kernel"),
            ),
            (
                "CentOS Plus Linux Server release 7.9",
                Version(7, 9),
                "kernel-plus",
                "kernel",
                ("kernel-plus",),
            ),
        ),
    )
    def test_fix_default_kernel_converting_success(
        self,
        system_name,
        version,
        old_kernel,
        new_kernel,
        not_default_kernels,
        caplog,
        monkeypatch,
        fix_default_kernel_instance,
    ):
        monkeypatch.setattr(system_info, "name", system_name)
        monkeypatch.setattr(system_info, "arch", "x86_64")
        monkeypatch.setattr(system_info, "version", version)
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=%s\n" % old_kernel,
        )
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())

        fix_default_kernel_instance.run()

        warning_msgs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warning_msgs
        assert "Detected leftover boot kernel, changing to RHEL kernel" in warning_msgs[-1].message

        (filename, content), _ = utils.store_content_to_file.call_args
        kernel_file_lines = content.splitlines()

        assert "/etc/sysconfig/kernel" == filename
        assert "DEFAULTKERNEL=%s" % new_kernel in kernel_file_lines

        for kernel_name in not_default_kernels:
            assert "DEFAULTKERNEL=%s" % kernel_name not in kernel_file_lines

    @centos7
    def test_fix_default_kernel_with_no_incorrect_kernel(
        self, caplog, monkeypatch, fix_default_kernel_instance, pretend_os
    ):
        monkeypatch.setattr(
            utils,
            "get_file_content",
            lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL=kernel\n",
        )
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())

        fix_default_kernel_instance.run()

        info_records = [m for m in caplog.records if m.levelname == "INFO"]
        warning_records = [m for m in caplog.records if m.levelname == "WARNING"]
        debug_records = [m for m in caplog.records if m.levelname == "DEBUG"]

        assert not warning_records
        assert any("Boot kernel validated." in r.message for r in debug_records)

        for record in info_records:
            assert not re.search("Boot kernel [^ ]\\+ was changed to [^ ]\\+", record.message)
