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

__metaclass__ = type

import os
import sys

import pytest
import six

from convert2rhel import backup


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import actions, applock, backup, checks, exceptions, grub, hostmetering
from convert2rhel import logger as logger_module
from convert2rhel import main, pkghandler, pkgmanager, redhatrelease, subscription, toolopts, unit_tests, utils
from convert2rhel.actions import report
from convert2rhel.breadcrumbs import breadcrumbs
from convert2rhel.systeminfo import system_info
from convert2rhel.unit_tests import (
    ClearVersionlockMocked,
    CLIMocked,
    CollectEarlyDataMocked,
    FinishCollectionMocked,
    InitializeFileLoggingMocked,
    MainLockedMocked,
    PrintDataCollectionMocked,
    PrintSystemInformationMocked,
    RequireRootMocked,
    ResolveSystemInfoMocked,
    RollbackChangesMocked,
    ShowEulaMocked,
    SummaryAsJsonMocked,
)


class TestRollbackChanges:
    def test_rollback_changes(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(global_backup_control, "pop_all", mock.Mock())

        main.rollback_changes()

        # Note: when we remove the BackupController partition hack, the first
        # of these calls will go away
        assert global_backup_control.pop_all.call_args_list == [mock.call(), mock.call()]

    def test_backup_control_unknown_exception(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(
            global_backup_control,
            "pop_all",
            mock.Mock(side_effect=([], IndexError("Raised because of a bug in the code"))),
        )

        with pytest.raises(IndexError, match="Raised because of a bug in the code"):
            main.rollback_changes()


@pytest.mark.parametrize(("exception_type", "exception"), ((IOError, True), (OSError, True), (None, False)))
def test_initialize_file_logging(exception_type, exception, monkeypatch, caplog):
    add_file_handler_mock = mock.Mock()
    archive_old_logger_files_mock = mock.Mock()

    if exception:
        archive_old_logger_files_mock.side_effect = exception_type

    monkeypatch.setattr(
        logger_module,
        "add_file_handler",
        value=add_file_handler_mock,
    )
    monkeypatch.setattr(
        logger_module,
        "archive_old_logger_files",
        value=archive_old_logger_files_mock,
    )

    main.initialize_file_logging("convert2rhel.log", "/tmp")

    if exception:
        assert caplog.records[-1].levelname == "WARNING"
        assert "Unable to archive previous log:" in caplog.records[-1].message

    add_file_handler_mock.assert_called_once()
    archive_old_logger_files_mock.assert_called_once()


class TestShowEula:
    eula_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "data", "version-independent"))

    def test_show_eula(self, monkeypatch):
        monkeypatch.setattr(utils, "DATA_DIR", self.eula_dir)

        main.show_eula()

    def test_show_eula_nonexisting_file(self, caplog, monkeypatch, tmpdir):
        # Needed in case convert2rhel is installed on this system
        monkeypatch.setattr(utils, "DATA_DIR", str(tmpdir))

        with pytest.raises(SystemExit, match="EULA file not found"):
            main.show_eula()

        assert caplog.records[-1].levelname == "CRITICAL"
        assert len(caplog.records) == 1


def test_post_ponr_conversion(monkeypatch):
    perserve_only_rhel_kernel_mock = mock.Mock()
    create_transaction_handler_mock = mock.Mock()
    list_non_red_hat_pkgs_left_mock = mock.Mock()
    post_ponr_set_efi_configuration_mock = mock.Mock()
    yum_conf_patch_mock = mock.Mock()
    lock_releasever_in_rhel_repositories_mock = mock.Mock()

    monkeypatch.setattr(pkghandler, "preserve_only_rhel_kernel", perserve_only_rhel_kernel_mock)
    monkeypatch.setattr(pkgmanager, "create_transaction_handler", create_transaction_handler_mock)
    monkeypatch.setattr(pkghandler, "list_non_red_hat_pkgs_left", list_non_red_hat_pkgs_left_mock)
    monkeypatch.setattr(grub, "post_ponr_set_efi_configuration", post_ponr_set_efi_configuration_mock)
    monkeypatch.setattr(redhatrelease.YumConf, "patch", yum_conf_patch_mock)
    monkeypatch.setattr(subscription, "lock_releasever_in_rhel_repositories", lock_releasever_in_rhel_repositories_mock)
    main.post_ponr_conversion()

    assert perserve_only_rhel_kernel_mock.call_count == 1
    assert create_transaction_handler_mock.call_count == 1
    assert list_non_red_hat_pkgs_left_mock.call_count == 1
    assert post_ponr_set_efi_configuration_mock.call_count == 1
    assert yum_conf_patch_mock.call_count == 1
    assert lock_releasever_in_rhel_repositories_mock.call_count == 1


def test_help_exit(monkeypatch, tmp_path):
    """
    Check that --help exits before we enter main_locked().

    We need special handling to deal with --help's exit if it occurs inside of the try: except in
    main_locked(). (Consult git history for main.py if the special handling needs to be resurrected.
    """
    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["convert2rhel", "--help"])
    monkeypatch.setattr(utils, "require_root", RequireRootMocked())
    monkeypatch.setattr(main, "initialize_file_logging", InitializeFileLoggingMocked())
    monkeypatch.setattr(main, "main_locked", MainLockedMocked())

    with pytest.raises(SystemExit):
        main.main()

    assert main.main_locked.call_count == 0


def test_main(monkeypatch, tmp_path):
    require_root_mock = mock.Mock()
    initialize_file_logging_mock = mock.Mock()
    toolopts_cli_mock = mock.Mock()
    show_eula_mock = mock.Mock()
    print_data_collection_mock = mock.Mock()
    resolve_system_info_mock = mock.Mock()
    print_system_information_mock = mock.Mock()
    collect_early_data_mock = mock.Mock()
    clean_yum_metadata_mock = mock.Mock()
    run_actions_mock = mock.Mock()
    find_actions_of_severity_mock = mock.Mock(return_value=[])
    clear_versionlock_mock = mock.Mock()
    report_summary_mock = mock.Mock()
    ask_to_continue_mock = mock.Mock()
    post_ponr_conversion_mock = mock.Mock()
    rpm_files_diff_mock = mock.Mock()
    update_grub_after_conversion_mock = mock.Mock()
    remove_tmp_dir_mock = mock.Mock()
    restart_system_mock = mock.Mock()
    finish_collection_mock = mock.Mock()
    check_kernel_boot_files_mock = mock.Mock()
    update_rhsm_custom_facts_mock = mock.Mock()
    summary_as_json_mock = mock.Mock()
    summary_as_txt_mock = mock.Mock()
    configure_host_metering_mock = mock.Mock()

    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
    monkeypatch.setattr(utils, "require_root", require_root_mock)
    monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
    monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
    monkeypatch.setattr(main, "show_eula", show_eula_mock)
    monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
    monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
    monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
    monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
    monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
    monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
    monkeypatch.setattr(actions, "run_actions", run_actions_mock)
    monkeypatch.setattr(actions, "find_actions_of_severity", find_actions_of_severity_mock)
    monkeypatch.setattr(report, "summary", report_summary_mock)
    monkeypatch.setattr(utils, "ask_to_continue", ask_to_continue_mock)
    monkeypatch.setattr(main, "post_ponr_conversion", post_ponr_conversion_mock)
    monkeypatch.setattr(system_info, "modified_rpm_files_diff", rpm_files_diff_mock)
    monkeypatch.setattr(grub, "update_grub_after_conversion", update_grub_after_conversion_mock)
    monkeypatch.setattr(utils, "remove_tmp_dir", remove_tmp_dir_mock)
    monkeypatch.setattr(utils, "restart_system", restart_system_mock)
    monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
    monkeypatch.setattr(checks, "check_kernel_boot_files", check_kernel_boot_files_mock)
    monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
    monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
    monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)
    monkeypatch.setattr(hostmetering, "configure_host_metering", configure_host_metering_mock)

    assert main.main() == 0
    assert require_root_mock.call_count == 1
    assert initialize_file_logging_mock.call_count == 1
    assert toolopts_cli_mock.call_count == 1
    assert show_eula_mock.call_count == 1
    assert print_data_collection_mock.call_count == 1
    assert resolve_system_info_mock.call_count == 1
    assert collect_early_data_mock.call_count == 1
    assert clean_yum_metadata_mock.call_count == 1
    assert find_actions_of_severity_mock.call_count == 1
    assert run_actions_mock.call_count == 1
    assert clear_versionlock_mock.call_count == 1
    assert report_summary_mock.call_count == 1
    assert ask_to_continue_mock.call_count == 1
    assert post_ponr_conversion_mock.call_count == 1
    assert rpm_files_diff_mock.call_count == 1
    assert remove_tmp_dir_mock.call_count == 1
    assert restart_system_mock.call_count == 1
    assert finish_collection_mock.call_count == 1
    assert check_kernel_boot_files_mock.call_count == 1
    assert update_rhsm_custom_facts_mock.call_count == 1
    assert summary_as_json_mock.call_count == 1
    assert summary_as_txt_mock.call_count == 1


class TestRollbackFromMain:
    def test_main_rollback_post_cli_phase(self, monkeypatch, caplog, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        toolopts_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock(side_effect=Exception)

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert toolopts_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert "No changes were made to the system." in caplog.records[-2].message

    def test_main_traceback_in_clear_versionlock(self, caplog, monkeypatch, tmp_path):
        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", RequireRootMocked())
        monkeypatch.setattr(main, "initialize_file_logging", InitializeFileLoggingMocked())
        monkeypatch.setattr(toolopts, "CLI", CLIMocked())
        monkeypatch.setattr(main, "show_eula", ShowEulaMocked())
        monkeypatch.setattr(breadcrumbs, "print_data_collection", PrintDataCollectionMocked())
        monkeypatch.setattr(system_info, "resolve_system_info", ResolveSystemInfoMocked())
        monkeypatch.setattr(system_info, "print_system_information", PrintSystemInformationMocked())
        monkeypatch.setattr(breadcrumbs, "collect_early_data", CollectEarlyDataMocked())
        monkeypatch.setattr(
            pkghandler,
            "clear_versionlock",
            ClearVersionlockMocked(
                side_effect=exceptions.CriticalError(
                    id_="TestError", title="A Title", description="Long description", diagnosis="Clearing lock failed"
                )
            ),
        )

        # And mock rollback items
        monkeypatch.setattr(breadcrumbs, "finish_collection", FinishCollectionMocked())
        monkeypatch.setattr(main, "rollback_changes", RollbackChangesMocked())
        monkeypatch.setattr(report, "summary_as_json", SummaryAsJsonMocked())

        assert main.main() == 1
        assert utils.require_root.call_count == 1
        assert toolopts.CLI.call_count == 1
        assert main.show_eula.call_count == 1
        assert breadcrumbs.print_data_collection.call_count == 1
        assert system_info.resolve_system_info.call_count == 1
        assert breadcrumbs.collect_early_data.call_count == 1
        assert pkghandler.clear_versionlock.call_count == 1

        assert caplog.records[-2].levelname == "INFO"
        assert caplog.records[-2].message.strip() == "No changes were made to the system."

        critical_logs = [log for log in caplog.records if log.levelname == "CRITICAL"]
        assert len(critical_logs) == 1
        assert critical_logs[0].message == "Clearing lock failed"

    def test_main_traceback_before_action_completion(self, monkeypatch, caplog, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        toolopts_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_actions_mock = mock.Mock(side_effect=Exception("Action Framework Crashed"))
        clear_versionlock_mock = mock.Mock()
        summary_as_txt_mock = mock.Mock()

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()
        should_subscribe_mock = mock.Mock(side_effect=lambda: False)
        update_rhsm_custom_facts_mock = mock.Mock()
        rollback_changes_mock = mock.Mock()
        summary_as_json_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_actions", run_actions_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "should_subscribe", should_subscribe_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(main, "rollback_changes", rollback_changes_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert toolopts_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_actions_mock.call_count == 1
        assert clear_versionlock_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert should_subscribe_mock.call_count == 1
        assert update_rhsm_custom_facts_mock.call_count == 1
        assert rollback_changes_mock.call_count == 1
        assert summary_as_json_mock.call_count == 0
        assert summary_as_txt_mock.call_count == 0
        assert (
            caplog.records[-2].message.strip()
            == "Conversion interrupted before analysis of system completed. Report not generated."
        )
        assert "Action Framework Crashed" in caplog.records[-3].message

    def test_main_rollback_pre_ponr_changes_phase(self, monkeypatch, caplog, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        toolopts_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_actions_mock = mock.Mock()
        report_summary_mock = mock.Mock()
        clear_versionlock_mock = mock.Mock()
        find_actions_of_severity_mock = mock.Mock()
        summary_as_txt_mock = mock.Mock()

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()
        should_subscribe_mock = mock.Mock(side_effect=lambda: False)
        update_rhsm_custom_facts_mock = mock.Mock()
        rollback_changes_mock = mock.Mock()
        summary_as_json_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_actions", run_actions_mock)
        monkeypatch.setattr(report, "summary", report_summary_mock)
        monkeypatch.setattr(actions, "find_actions_of_severity", find_actions_of_severity_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "should_subscribe", should_subscribe_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(main, "rollback_changes", rollback_changes_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert toolopts_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_actions_mock.call_count == 1
        assert report_summary_mock.call_count == 1
        assert find_actions_of_severity_mock.call_count == 1
        assert clear_versionlock_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert should_subscribe_mock.call_count == 1
        assert update_rhsm_custom_facts_mock.call_count == 1
        assert rollback_changes_mock.call_count == 1
        assert summary_as_json_mock.call_count == 1
        assert summary_as_txt_mock.call_count == 1
        assert caplog.records[-3].message == "Conversion failed."
        assert caplog.records[-3].levelname == "CRITICAL"

    def test_main_rollback_analyze_exit_phase_without_subman(self, global_tool_opts, monkeypatch, tmp_path):
        """
        This test is the opposite of
        `py:test_main_rollback_analyze_exit_phase`, where we are checking the
        case that the system needs to be registered during the analyze.

        If that's the case, we don't want to call the update_rhsm_custom_facts
        as the system will be unregistered in the end.
        """
        mocks = (
            (applock, "_DEFAULT_LOCK_DIR", str(tmp_path)),
            (utils, "require_root", mock.Mock()),
            (main, "initialize_file_logging", mock.Mock()),
            (toolopts, "CLI", mock.Mock()),
            (main, "show_eula", mock.Mock()),
            (breadcrumbs, "print_data_collection", mock.Mock()),
            (system_info, "resolve_system_info", mock.Mock()),
            (system_info, "print_system_information", mock.Mock()),
            (breadcrumbs, "collect_early_data", mock.Mock()),
            (pkghandler, "clear_versionlock", mock.Mock()),
            (pkgmanager, "clean_yum_metadata", mock.Mock()),
            (actions, "run_actions", mock.Mock()),
            (report, "summary", mock.Mock()),
            (breadcrumbs, "finish_collection", mock.Mock()),
            (subscription, "should_subscribe", mock.Mock(side_effect=lambda: True)),
            (subscription, "update_rhsm_custom_facts", mock.Mock()),
            (main, "rollback_changes", mock.Mock()),
            (os, "environ", {"CONVERT2RHEL_EXPERIMENTAL_ANALYSIS": 1}),
            (report, "summary_as_json", mock.Mock()),
            (report, "summary_as_txt", mock.Mock()),
        )
        global_tool_opts.activity = "analysis"
        for module, function, value in mocks:
            monkeypatch.setattr(module, function, value)

        assert main.main() == 0
        assert utils.require_root.call_count == 1
        assert toolopts.CLI.call_count == 1
        assert main.show_eula.call_count == 1
        assert breadcrumbs.print_data_collection.call_count == 1
        assert system_info.resolve_system_info.call_count == 1
        assert system_info.print_system_information.call_count == 1
        assert breadcrumbs.collect_early_data.call_count == 1
        assert pkghandler.clear_versionlock.call_count == 1
        assert pkgmanager.clean_yum_metadata.call_count == 1
        assert actions.run_actions.call_count == 1
        assert report.summary.call_count == 1
        assert breadcrumbs.finish_collection.call_count == 1
        assert subscription.should_subscribe.call_count == 1
        assert subscription.update_rhsm_custom_facts.call_count == 0
        assert main.rollback_changes.call_count == 1
        assert report.summary_as_json.call_count == 1
        assert report.summary_as_txt.call_count == 1

    def test_main_rollback_analyze_exit_phase(self, global_tool_opts, monkeypatch, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        toolopts_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_actions_mock = mock.Mock()
        report_summary_mock = mock.Mock()
        clear_versionlock_mock = mock.Mock()
        summary_as_json_mock = mock.Mock()
        summary_as_txt_mock = mock.Mock()

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()
        should_subscribe_mock = mock.Mock(side_effect=lambda: False)
        update_rhsm_custom_facts_mock = mock.Mock()
        rollback_changes_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_actions", run_actions_mock)
        monkeypatch.setattr(report, "summary", report_summary_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "should_subscribe", should_subscribe_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(main, "rollback_changes", rollback_changes_mock)
        monkeypatch.setattr(os, "environ", {"CONVERT2RHEL_EXPERIMENTAL_ANALYSIS": 1})
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)
        global_tool_opts.activity = "analysis"

        assert main.main() == 0
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert toolopts_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_actions_mock.call_count == 1
        assert report_summary_mock.call_count == 1
        assert clear_versionlock_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert should_subscribe_mock.call_count == 1
        assert update_rhsm_custom_facts_mock.call_count == 1
        assert rollback_changes_mock.call_count == 1
        assert summary_as_json_mock.call_count == 1
        assert summary_as_txt_mock.call_count == 1

    def test_main_rollback_post_ponr_changes_phase(self, monkeypatch, caplog, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        toolopts_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_actions_mock = mock.Mock()
        find_actions_of_severity_mock = mock.Mock(return_value=[])
        report_summary_mock = mock.Mock()
        clear_versionlock_mock = mock.Mock()
        ask_to_continue_mock = mock.Mock()
        post_ponr_conversion_mock = mock.Mock(side_effect=Exception)
        summary_as_json_mock = mock.Mock()
        summary_as_txt_mock = mock.Mock()

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()
        update_rhsm_custom_facts_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(toolopts, "CLI", toolopts_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_actions", run_actions_mock)
        monkeypatch.setattr(actions, "find_actions_of_severity", find_actions_of_severity_mock)
        monkeypatch.setattr(report, "summary", report_summary_mock)
        monkeypatch.setattr(utils, "ask_to_continue", ask_to_continue_mock)
        monkeypatch.setattr(main, "post_ponr_conversion", post_ponr_conversion_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert toolopts_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_actions_mock.call_count == 1
        assert find_actions_of_severity_mock.call_count == 1
        assert clear_versionlock_mock.call_count == 1
        assert report_summary_mock.call_count == 1
        assert ask_to_continue_mock.call_count == 1
        assert post_ponr_conversion_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert summary_as_json_mock.call_count == 1
        assert summary_as_txt_mock.call_count == 1
        assert "The system is left in an undetermined state that Convert2RHEL cannot fix." in caplog.records[-2].message
        assert update_rhsm_custom_facts_mock.call_count == 1
