# -*- coding: utf-8 -*-
#
# Copyright(C) 2016 Red Hat, Inc.
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
import sys
import unittest

from collections import OrderedDict

import pytest
import six

from convert2rhel import backup, grub
from convert2rhel import logger as logger_module
from convert2rhel import pkghandler, redhatrelease, repo, special_cases, subscription, toolopts, utils
from convert2rhel.breadcrumbs import breadcrumbs
from convert2rhel.redhatrelease import os_release_file, system_release_file
from convert2rhel.systeminfo import system_info


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import cert, checks
from convert2rhel import logger as logger_module
from convert2rhel import main, pkghandler, redhatrelease, repo, special_cases, subscription, unit_tests, utils
from convert2rhel.toolopts import tool_opts


def mock_calls(class_or_module, method_name, mock_obj):
    return unit_tests.mock(class_or_module, method_name, mock_obj(method_name))


class TestMain(unittest.TestCase):
    class AskToContinueMocked(unit_tests.MockFunction):
        def __call__(self, *args, **kwargs):
            return

    eula_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "data", "version-independent"))

    @unit_tests.mock(utils, "DATA_DIR", eula_dir)
    def test_show_eula(self):
        main.show_eula()

    class GetFakeFunctionMocked(unit_tests.MockFunction):
        def __call__(self, filename):
            pass

    class GetFileContentMocked(unit_tests.MockFunction):
        def __call__(self, filename):
            return utils.get_file_content_orig(unit_tests.NONEXISTING_FILE)

    class GetLoggerMocked(unit_tests.MockFunction):
        def __init__(self):
            self.info_msgs = []
            self.critical_msgs = []

        def __call__(self, msg):
            return self

        def task(self, msg):
            pass

        def critical(self, msg):
            self.critical_msgs.append(msg)
            raise SystemExit(1)

        def info(self, msg):
            pass

        def debug(self, msg):
            pass

    class CallOrderMocked(unit_tests.MockFunction):
        calls = OrderedDict()

        def __init__(self, method_name):
            self.method_name = method_name

        def __call__(self, *args):
            self.add_call(self.method_name)
            return args

        @classmethod
        def add_call(cls, method_name):
            if method_name in cls.calls:
                cls.calls[method_name] += 1
            else:
                cls.calls[method_name] = 1

        @classmethod
        def reset(cls):
            cls.calls = OrderedDict()

    class CallYumCmdMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0
            self.return_code = 0
            self.return_string = "Test output"
            self.fail_once = False
            self.command = None
            self.args = None

        def __call__(self, command, args):
            if self.fail_once and self.called == 0:
                self.return_code = 1
            if self.fail_once and self.called > 0:
                self.return_code = 0
            self.called += 1
            self.command = command
            self.args = args
            return self.return_string, self.return_code

    @unit_tests.mock(main, "loggerinst", GetLoggerMocked())
    @unit_tests.mock(utils, "get_file_content", GetFileContentMocked())
    def test_show_eula_nonexisting_file(self):
        self.assertRaises(SystemExit, main.show_eula)
        self.assertEqual(len(main.loggerinst.critical_msgs), 1)

    @unit_tests.mock(
        backup.changed_pkgs_control,
        "restore_pkgs",
        unit_tests.CountableMockObject(),
    )
    @unit_tests.mock(
        redhatrelease.system_release_file,
        "restore",
        unit_tests.CountableMockObject(),
    )
    @unit_tests.mock(
        redhatrelease.os_release_file,
        "restore",
        unit_tests.CountableMockObject(),
    )
    @unit_tests.mock(
        special_cases.shim_x64_pkg_protection_file,
        "restore",
        unit_tests.CountableMockObject(),
    )
    @unit_tests.mock(repo, "restore_yum_repos", unit_tests.CountableMockObject())
    @unit_tests.mock(subscription, "rollback", unit_tests.CountableMockObject())
    @unit_tests.mock(
        pkghandler.versionlock_file,
        "restore",
        unit_tests.CountableMockObject(),
    )
    @unit_tests.mock(cert.SystemCert, "_get_cert", lambda _get_cert: ("anything", "anything"))
    @unit_tests.mock(cert.SystemCert, "remove", unit_tests.CountableMockObject())
    def test_rollback_changes(self):
        main.rollback_changes()
        self.assertEqual(backup.changed_pkgs_control.restore_pkgs.called, 1)
        self.assertEqual(repo.restore_yum_repos.called, 1)
        self.assertEqual(redhatrelease.system_release_file.restore.called, 1)
        self.assertEqual(redhatrelease.os_release_file.restore.called, 1)
        self.assertEqual(special_cases.shim_x64_pkg_protection_file.restore.called, 1)
        self.assertEqual(subscription.rollback.called, 1)
        self.assertEqual(pkghandler.versionlock_file.restore.called, 1)
        self.assertEqual(cert.SystemCert.remove.called, 1)

    @unit_tests.mock(main.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "no_rhsm", False)
    @unit_tests.mock(cert.SystemCert, "_get_cert", lambda _get_cert: ("anything", "anything"))
    @mock_calls(main.special_cases, "check_and_resolve", CallOrderMocked)
    @mock_calls(main.checks, "perform_pre_checks", CallOrderMocked)
    @mock_calls(main.checks, "perform_pre_ponr_checks", CallOrderMocked)
    @mock_calls(pkghandler, "remove_excluded_pkgs", CallOrderMocked)
    @mock_calls(subscription, "replace_subscription_manager", CallOrderMocked)
    @mock_calls(subscription, "verify_rhsm_installed", CallOrderMocked)
    @mock_calls(pkghandler, "remove_repofile_pkgs", CallOrderMocked)
    @mock_calls(cert.SystemCert, "install", CallOrderMocked)
    @mock_calls(pkghandler, "list_third_party_pkgs", CallOrderMocked)
    @mock_calls(subscription, "subscribe_system", CallOrderMocked)
    @mock_calls(repo, "get_rhel_repoids", CallOrderMocked)
    @mock_calls(subscription, "check_needed_repos_availability", CallOrderMocked)
    @mock_calls(subscription, "disable_repos", CallOrderMocked)
    @mock_calls(subscription, "enable_repos", CallOrderMocked)
    @mock_calls(subscription, "download_rhsm_pkgs", CallOrderMocked)
    @unit_tests.mock(checks, "check_readonly_mounts", GetFakeFunctionMocked)
    def test_pre_ponr_conversion_order_with_rhsm(self):
        self.CallOrderMocked.reset()
        main.pre_ponr_conversion()

        intended_call_order = OrderedDict()
        intended_call_order["list_third_party_pkgs"] = 1
        intended_call_order["remove_excluded_pkgs"] = 1
        intended_call_order["check_and_resolve"] = 1
        intended_call_order["download_rhsm_pkgs"] = 1
        intended_call_order["replace_subscription_manager"] = 1
        intended_call_order["verify_rhsm_installed"] = 1
        intended_call_order["install"] = 1
        intended_call_order["subscribe_system"] = 1
        intended_call_order["get_rhel_repoids"] = 1
        intended_call_order["check_needed_repos_availability"] = 1
        intended_call_order["disable_repos"] = 1
        intended_call_order["remove_repofile_pkgs"] = 1
        intended_call_order["enable_repos"] = 1
        intended_call_order["perform_pre_ponr_checks"] = 1
        intended_call_order["perform_pre_checks"] = 1

        # Merge the two together like a zipper, creates a tuple which we can assert with - including method call order!
        zipped_call_order = zip(intended_call_order.items(), self.CallOrderMocked.calls.items())
        for expected, actual in zipped_call_order:
            if expected[1] > 0:
                self.assertEqual(expected, actual)

    @unit_tests.mock(main.logging, "getLogger", GetLoggerMocked())
    @unit_tests.mock(tool_opts, "no_rhsm", False)
    @unit_tests.mock(cert.SystemCert, "_get_cert", lambda _get_cert: ("anything", "anything"))
    @mock_calls(main.special_cases, "check_and_resolve", CallOrderMocked)
    @mock_calls(main.checks, "perform_pre_checks", CallOrderMocked)
    @mock_calls(main.checks, "perform_pre_ponr_checks", CallOrderMocked)
    @mock_calls(pkghandler, "remove_excluded_pkgs", CallOrderMocked)
    @mock_calls(subscription, "replace_subscription_manager", CallOrderMocked)
    @mock_calls(subscription, "verify_rhsm_installed", CallOrderMocked)
    @mock_calls(pkghandler, "remove_repofile_pkgs", CallOrderMocked)
    @mock_calls(cert.SystemCert, "install", CallOrderMocked)
    @mock_calls(pkghandler, "list_third_party_pkgs", CallOrderMocked)
    @mock_calls(subscription, "subscribe_system", CallOrderMocked)
    @mock_calls(repo, "get_rhel_repoids", CallOrderMocked)
    @mock_calls(subscription, "check_needed_repos_availability", CallOrderMocked)
    @mock_calls(subscription, "disable_repos", CallOrderMocked)
    @mock_calls(subscription, "enable_repos", CallOrderMocked)
    @mock_calls(subscription, "download_rhsm_pkgs", CallOrderMocked)
    @unit_tests.mock(checks, "check_readonly_mounts", GetFakeFunctionMocked)
    def test_pre_ponr_conversion_order_without_rhsm(self):
        self.CallOrderMocked.reset()
        main.pre_ponr_conversion()

        intended_call_order = OrderedDict()

        intended_call_order["list_third_party_pkgs"] = 1
        intended_call_order["remove_excluded_pkgs"] = 1
        intended_call_order["check_and_resolve"] = 1

        # Do not expect this one to be called - related to RHSM
        intended_call_order["download_rhsm_pkgs"] = 0
        intended_call_order["replace_subscription_manager"] = 0
        intended_call_order["verify_rhsm_installed"] = 0
        intended_call_order["install"] = 0
        intended_call_order["subscribe_system"] = 0
        intended_call_order["get_rhel_repoids"] = 0
        intended_call_order["check_needed_repos_availability"] = 0
        intended_call_order["disable_repos"] = 0

        intended_call_order["remove_repofile_pkgs"] = 1

        intended_call_order["enable_repos"] = 0

        intended_call_order["perform_pre_ponr_checks"] = 1

        # Merge the two together like a zipper, creates a tuple which we can assert with - including method call order!
        zipped_call_order = zip(intended_call_order.items(), self.CallOrderMocked.calls.items())
        for expected, actual in zipped_call_order:
            if expected[1] > 0:
                self.assertEqual(expected, actual)


@pytest.mark.parametrize(("exception_type", "exception"), ((IOError, True), (OSError, True), (None, False)))
def test_initialize_logger(exception_type, exception, monkeypatch, capsys):
    setup_logger_handler_mock = mock.Mock()
    archive_old_logger_files_mock = mock.Mock()

    if exception:
        archive_old_logger_files_mock.side_effect = exception_type

    monkeypatch.setattr(
        logger_module,
        "setup_logger_handler",
        value=setup_logger_handler_mock,
    )
    monkeypatch.setattr(
        logger_module,
        "archive_old_logger_files",
        value=archive_old_logger_files_mock,
    )

    if exception:
        main.initialize_logger("convert2rhel.log", "/tmp")
        out, _ = capsys.readouterr()
        assert "Warning: Unable to archive previous log:" in out
    else:
        main.initialize_logger("convert2rhel.log", "/tmp")
        setup_logger_handler_mock.assert_called_once()
        archive_old_logger_files_mock.assert_called_once()


def test_post_ponr_conversion(monkeypatch):
    install_gpg_keys_mock = mock.Mock()
    perserve_only_rhel_kernel_mock = mock.Mock()
    replace_non_red_hat_pkgs_left_mock = mock.Mock()
    list_non_red_hat_pkgs_left_mock = mock.Mock()
    post_ponr_set_efi_configuration_mock = mock.Mock()
    yum_conf_patch_mock = mock.Mock()
    lock_releasever_in_rhel_repositories_mock = mock.Mock()
    finish_success_mock = mock.Mock()

    monkeypatch.setattr(pkghandler, "install_gpg_keys", install_gpg_keys_mock)
    monkeypatch.setattr(pkghandler, "preserve_only_rhel_kernel", perserve_only_rhel_kernel_mock)
    monkeypatch.setattr(pkghandler, "replace_non_red_hat_packages", replace_non_red_hat_pkgs_left_mock)
    monkeypatch.setattr(pkghandler, "list_non_red_hat_pkgs_left", list_non_red_hat_pkgs_left_mock)
    monkeypatch.setattr(grub, "post_ponr_set_efi_configuration", post_ponr_set_efi_configuration_mock)
    monkeypatch.setattr(redhatrelease.YumConf, "patch", yum_conf_patch_mock)
    monkeypatch.setattr(subscription, "lock_releasever_in_rhel_repositories", lock_releasever_in_rhel_repositories_mock)
    monkeypatch.setattr(breadcrumbs, "finish_success", finish_success_mock)

    main.post_ponr_conversion()

    assert install_gpg_keys_mock.call_count == 1
    assert perserve_only_rhel_kernel_mock.call_count == 1
    assert replace_non_red_hat_pkgs_left_mock.call_count == 1
    assert list_non_red_hat_pkgs_left_mock.call_count == 1
    assert post_ponr_set_efi_configuration_mock.call_count == 1
    assert yum_conf_patch_mock.call_count == 1
    assert lock_releasever_in_rhel_repositories_mock.call_count == 1
    assert finish_success_mock.call_count == 1


def test_main(monkeypatch):
    require_root_mock = mock.Mock()
    initialize_logger_mock = mock.Mock()
    toolopts_cli_mock = mock.Mock()
    show_eula_mock = mock.Mock()
    resolve_system_info_mock = mock.Mock()
    collect_early_data_mock = mock.Mock()
    clean_yum_metadata_mock = mock.Mock()
    perform_pre_checks_mock = mock.Mock()
    system_release_file_mock = mock.Mock()
    os_release_file_mock = mock.Mock()
    backup_yum_repos_mock = mock.Mock()
    clear_versionlock_mock = mock.Mock()
    pre_ponr_conversion_mock = mock.Mock()
    ask_to_continue_mock = mock.Mock()
    post_ponr_conversion_mock = mock.Mock()
    rpm_files_diff_mock = mock.Mock()
    update_grub_after_conversion_mock = mock.Mock()
    remove_tmp_dir_mock = mock.Mock()
    restart_system_mock = mock.Mock()

    monkeypatch.setattr(utils, "require_root", require_root_mock)
    monkeypatch.setattr(main, "initialize_logger", initialize_logger_mock)
    monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
    monkeypatch.setattr(main, "show_eula", show_eula_mock)
    monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
    monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
    monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
    monkeypatch.setattr(pkghandler, "clean_yum_metadata", clean_yum_metadata_mock)
    monkeypatch.setattr(checks, "perform_pre_checks", perform_pre_checks_mock)
    monkeypatch.setattr(system_release_file, "backup", system_release_file_mock)
    monkeypatch.setattr(os_release_file, "backup", os_release_file_mock)
    monkeypatch.setattr(repo, "backup_yum_repos", backup_yum_repos_mock)
    monkeypatch.setattr(main, "pre_ponr_conversion", pre_ponr_conversion_mock)
    monkeypatch.setattr(utils, "ask_to_continue", ask_to_continue_mock)
    monkeypatch.setattr(main, "post_ponr_conversion", post_ponr_conversion_mock)
    monkeypatch.setattr(system_info, "modified_rpm_files_diff", rpm_files_diff_mock)
    monkeypatch.setattr(grub, "update_grub_after_conversion", update_grub_after_conversion_mock)
    monkeypatch.setattr(utils, "remove_tmp_dir", remove_tmp_dir_mock)
    monkeypatch.setattr(utils, "restart_system", restart_system_mock)

    assert main.main() == 0
    assert require_root_mock.call_count == 1
    assert initialize_logger_mock.call_count == 1
    assert toolopts_cli_mock.call_count == 1
    assert show_eula_mock.call_count == 1
    assert resolve_system_info_mock.call_count == 1
    assert collect_early_data_mock.call_count == 1
    assert clean_yum_metadata_mock.call_count == 1
    assert perform_pre_checks_mock.call_count == 1
    assert system_release_file_mock.call_count == 1
    assert os_release_file_mock.call_count == 1
    assert backup_yum_repos_mock.call_count == 1
    assert clear_versionlock_mock.call_count == 1
    assert pre_ponr_conversion_mock.call_count == 1
    assert ask_to_continue_mock.call_count == 1
    assert post_ponr_conversion_mock.call_count == 1
    assert rpm_files_diff_mock.call_count == 1
    assert remove_tmp_dir_mock.call_count == 1
    assert restart_system_mock.call_count == 1
