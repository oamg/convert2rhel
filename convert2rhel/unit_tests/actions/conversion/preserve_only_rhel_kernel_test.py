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
    GetInstalledPkgsByKeyIdMocked,
    GetInstalledPkgsWDifferentKeyIdMocked,
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
def fix_invalid_grub2_entries_instance():
    return preserve_only_rhel_kernel.FixInvalidGrub2Entries()


@pytest.fixture
def fix_default_kernel_instance():
    return preserve_only_rhel_kernel.FixDefaultKernel()


@pytest.fixture
def kernel_packages_install_instance():
    return preserve_only_rhel_kernel.KernelPkgsInstall()


@pytest.fixture
def update_kernel_instance():
    return preserve_only_rhel_kernel.UpdateKernel()


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(pkgmanager, "tool_opts", global_tool_opts)


class TestInstallRhelKernel:
    @pytest.mark.parametrize(
        (
            "pkgs_w_rhel_key_id",
            "no_newer_kernel_call",
        ),
        (
            (
                # rhel kernel not installed
                [],
                1,
            ),
            (
                # rhel kernel already installed
                [create_pkg_information(name="kernel")],
                0,
            ),
        ),
    )
    @centos8
    def test_install_rhel_kernel(
        self,
        monkeypatch,
        pkgs_w_rhel_key_id,
        install_rhel_kernel_instance,
        no_newer_kernel_call,
        pretend_os,
    ):
        """Test the logic of kernel installation"""
        handle_no_newer_rhel_kernel_available = mock.Mock()

        monkeypatch.setattr(pkghandler, "handle_no_newer_rhel_kernel_available", handle_no_newer_rhel_kernel_available)
        monkeypatch.setattr(
            pkghandler, "get_installed_pkgs_by_key_id", GetInstalledPkgsByKeyIdMocked(return_value=pkgs_w_rhel_key_id)
        )

        install_rhel_kernel_instance.run()

        assert handle_no_newer_rhel_kernel_available.call_count == no_newer_kernel_call

    def test_verify_rhel_kernel_installed(self, monkeypatch, install_rhel_kernel_instance, caplog):
        monkeypatch.setattr(
            pkghandler,
            "get_installed_pkgs_by_key_id",
            GetInstalledPkgsByKeyIdMocked(return_value=[create_pkg_information(name="kernel")]),
        )
        install_rhel_kernel_instance.run()

        assert "RHEL kernel has been verified to be on the system." in caplog.text

    def test_verify_rhel_kernel_installed_not_installed(self, monkeypatch, install_rhel_kernel_instance):
        monkeypatch.setattr(pkghandler, "get_installed_pkgs_by_key_id", mock.Mock(return_value=[]))
        monkeypatch.setattr(pkghandler, "handle_no_newer_rhel_kernel_available", mock.Mock())

        install_rhel_kernel_instance.run()
        unit_tests.assert_actions_result(
            install_rhel_kernel_instance,
            level="ERROR",
            id="NO_RHEL_KERNEL_INSTALLED",
            title="No RHEL kernel installed",
            description="There is no RHEL kernel installed on the system.",
            remediations="Verify that the repository used for installing kernel contains RHEL packages and install the"
            " kernel manually.",
        )


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
            "get_installed_pkgs_w_different_key_id",
            GetInstalledPkgsWDifferentKeyIdMocked(pkg_selection="kernels"),
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
            "get_installed_pkgs_w_different_key_id",
            GetInstalledPkgsWDifferentKeyIdMocked(pkg_selection="kernels"),
        )
        monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
        monkeypatch.setattr(utils, "remove_pkgs", RemovePkgsMocked())
        monkeypatch.setattr(pkgmanager, "call_yum_cmd", CallYumCmdMocked())

        removed_pkgs = kernel_packages_install_instance.remove_non_rhel_kernels()
        kernel_packages_install_instance.install_additional_rhel_kernel_pkgs(removed_pkgs)
        assert pkgmanager.call_yum_cmd.call_count == 2


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
            lambda _: "UPDATEDEFAULT=yes\nDEFAULTKERNEL={}\n".format(old_kernel),
        )
        monkeypatch.setattr(utils, "store_content_to_file", StoreContentToFileMocked())

        fix_default_kernel_instance.run()

        warning_msgs = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warning_msgs
        assert "Detected leftover boot kernel, changing to RHEL kernel" in warning_msgs[-1].message

        (filename, content), _ = utils.store_content_to_file.call_args
        kernel_file_lines = content.splitlines()

        assert "/etc/sysconfig/kernel" == filename
        assert "DEFAULTKERNEL={}".format(new_kernel) in kernel_file_lines

        for kernel_name in not_default_kernels:
            assert "DEFAULTKERNEL={}".format(kernel_name) not in kernel_file_lines

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


class TestUpdateKernel:
    @pytest.mark.parametrize(
        ("update_kernel"),
        ((True),),
    )
    @centos8
    def test_update_kernel(self, monkeypatch, update_kernel_instance, update_kernel, pretend_os):
        update_rhel_kernel = mock.Mock()
        monkeypatch.setattr(pkghandler, "update_rhel_kernel", update_rhel_kernel)

        update_kernel_instance.run()

        assert (update_rhel_kernel.call_count == 1) == update_kernel
