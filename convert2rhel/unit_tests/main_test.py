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


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import actions, applock, backup, cli, exceptions
from convert2rhel import logger as logger_module
from convert2rhel import main, pkghandler, pkgmanager, subscription, toolopts, utils
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
    PrintInfoAfterRollbackMocked,
    PrintSystemInformationMocked,
    RequireRootMocked,
    ResolveSystemInfoMocked,
    RollbackChangesMocked,
    ShowEulaMocked,
    SummaryAsJsonMocked,
)


@pytest.fixture(autouse=True)
def apply_global_tool_opts(monkeypatch, global_tool_opts):
    monkeypatch.setattr(main, "tool_opts", global_tool_opts)


class TestRollbackChanges:
    def test_rollback_changes(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(global_backup_control, "pop_all", mock.Mock())

        main.rollback_changes()

        assert global_backup_control.pop_all.call_args_list == mock.call()
        assert backup.backup_control.rollback_failed is False

    def test_backup_control_unknown_exception(self, monkeypatch, global_backup_control):
        monkeypatch.setattr(
            global_backup_control,
            "pop_all",
            mock.Mock(side_effect=IndexError("Raised because of a bug in the code")),
        )

        with pytest.raises(IndexError, match="Raised because of a bug in the code"):
            main.rollback_changes()

    @pytest.mark.parametrize(
        ("pre_conversion_results", "include_all_reports", "rollback_failures", "message", "not_printed_message"),
        (
            (
                "anything",
                False,
                ["rollback_fail_0", "rollback_fail_1", "rollback_fail_2", "rollback_fail_3"],
                "Rollback of system wasn't completed successfully.\n"
                "The system is left in an undetermined state that Convert2RHEL cannot fix.\n"
                "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore"
                " the system from a backup.\n"
                "Following errors were captured during rollback:\n"
                "rollback_fail_0\n"
                "rollback_fail_1\n"
                "rollback_fail_2\n"
                "rollback_fail_3",
                [
                    "\nConversion interrupted before analysis of system completed. Report not generated.\n",
                    "No problems detected during the analysis!\n",
                ],
            ),
            (
                "anything",
                False,
                ["rollback_fail_0"],
                "Rollback of system wasn't completed successfully.\n"
                "The system is left in an undetermined state that Convert2RHEL cannot fix.\n"
                "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore"
                " the system from a backup.\n"
                "Following errors were captured during rollback:\n"
                "rollback_fail_0",
                [
                    "\nConversion interrupted before analysis of system completed. Report not generated.\n",
                    "No problems detected during the analysis!\n",
                ],
            ),
            (
                {
                    "PreSubscription": {
                        "messages": [],
                        "result": {
                            "level": actions.STATUS_CODE["SUCCESS"],
                            "id": "SUCCESS",
                            "title": "",
                            "description": "",
                            "diagnosis": "",
                            "remediations": "",
                            "variables": {},
                        },
                    }
                },
                False,
                [],
                "No problems detected!\n",
                [
                    "Rollback of system wasn't completed successfully.\n",
                    "\nConversion interrupted before analysis of system completed. Report not generated.\n",
                ],
            ),
            (
                None,
                True,
                [],
                "\nConversion interrupted before analysis of system completed. Report not generated.\n",
                ["Rollback of system wasn't completed successfully.\n", "No problems detected during the analysis!\n"],
            ),
        ),
    )
    def test_provide_status_after_rollback(
        self,
        monkeypatch,
        caplog,
        pre_conversion_results,
        include_all_reports,
        message,
        global_backup_control,
        rollback_failures,
        not_printed_message,
    ):
        monkeypatch.setattr(global_backup_control, "_rollback_failures", rollback_failures)

        main.provide_status_after_rollback(pre_conversion_results, include_all_reports)

        assert message == caplog.records[-1].message
        for not_printed in not_printed_message:
            assert not_printed not in caplog.text


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


def test_main(monkeypatch, global_tool_opts, tmp_path):
    require_root_mock = mock.Mock()
    initialize_file_logging_mock = mock.Mock()
    cli_cli_mock = mock.Mock()
    show_eula_mock = mock.Mock()
    print_data_collection_mock = mock.Mock()
    resolve_system_info_mock = mock.Mock()
    print_system_information_mock = mock.Mock()
    collect_early_data_mock = mock.Mock()
    clean_yum_metadata_mock = mock.Mock()
    raise_for_skipped_failures_mock = mock.Mock()
    report_summary_mock = mock.Mock()
    run_pre_actions_mock = mock.Mock()
    run_post_actions_mock = mock.Mock()
    clear_versionlock_mock = mock.Mock()
    ask_to_continue_mock = mock.Mock()
    restart_system_mock = mock.Mock()
    summary_as_json_mock = mock.Mock()
    summary_as_txt_mock = mock.Mock()

    monkeypatch.setattr(subscription, "tool_opts", global_tool_opts)
    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
    monkeypatch.setattr(utils, "require_root", require_root_mock)
    monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
    monkeypatch.setattr(cli, "CLI", cli_cli_mock)
    monkeypatch.setattr(main, "show_eula", show_eula_mock)
    monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
    monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
    monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
    monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
    monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
    monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
    monkeypatch.setattr(actions, "run_pre_actions", run_pre_actions_mock)
    monkeypatch.setattr(actions, "run_post_actions", run_post_actions_mock)
    monkeypatch.setattr(main, "_raise_for_skipped_failures", raise_for_skipped_failures_mock)
    monkeypatch.setattr(report, "_summary", report_summary_mock)
    monkeypatch.setattr(utils, "ask_to_continue", ask_to_continue_mock)
    monkeypatch.setattr(utils, "restart_system", restart_system_mock)
    monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
    monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)

    assert main.main() == 0
    assert require_root_mock.call_count == 1
    assert initialize_file_logging_mock.call_count == 1
    assert cli_cli_mock.call_count == 1
    assert show_eula_mock.call_count == 1
    assert print_data_collection_mock.call_count == 1
    assert resolve_system_info_mock.call_count == 1
    assert collect_early_data_mock.call_count == 1
    assert clean_yum_metadata_mock.call_count == 1
    assert run_pre_actions_mock.call_count == 1
    assert run_post_actions_mock.call_count == 1
    assert raise_for_skipped_failures_mock.call_count == 2
    assert report_summary_mock.call_count == 2
    assert clear_versionlock_mock.call_count == 1
    assert ask_to_continue_mock.call_count == 1
    assert restart_system_mock.call_count == 1
    assert summary_as_json_mock.call_count == 1
    assert summary_as_txt_mock.call_count == 1


class TestRollbackFromMain:
    def test_main_rollback_post_cli_phase(self, monkeypatch, caplog, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        cli_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock(side_effect=Exception)
        finish_collection_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(cli, "CLI", cli_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert cli_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert "No changes were made to the system." in caplog.records[-2].message

    def test_main_traceback_in_clear_versionlock(self, caplog, monkeypatch, tmp_path):
        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", RequireRootMocked())
        monkeypatch.setattr(main, "initialize_file_logging", InitializeFileLoggingMocked())
        monkeypatch.setattr(cli, "CLI", CLIMocked())
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

        # Mock rollback items
        monkeypatch.setattr(main, "rollback_changes", RollbackChangesMocked())
        monkeypatch.setattr(main, "provide_status_after_rollback", PrintInfoAfterRollbackMocked())

        monkeypatch.setattr(breadcrumbs, "finish_collection", FinishCollectionMocked())
        monkeypatch.setattr(report, "summary_as_json", SummaryAsJsonMocked())

        assert main.main() == 1
        assert utils.require_root.call_count == 1
        assert cli.CLI.call_count == 1
        assert main.show_eula.call_count == 1
        assert breadcrumbs.print_data_collection.call_count == 1
        assert system_info.resolve_system_info.call_count == 1
        assert breadcrumbs.collect_early_data.call_count == 1
        assert pkghandler.clear_versionlock.call_count == 1

        assert main.rollback_changes.call_count == 0
        assert main.provide_status_after_rollback.call_count == 0

        assert caplog.records[-2].message.strip() == "No changes were made to the system."
        assert caplog.records[-2].levelname == "INFO"

        critical_logs = [log for log in caplog.records if log.levelname == "CRITICAL"]
        assert len(critical_logs) == 1
        assert critical_logs[0].message == "Clearing lock failed"

    def test_main_traceback_before_action_completion(self, monkeypatch, caplog, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        cli_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_pre_actions_mock = mock.Mock(side_effect=Exception("Action Framework Crashed"))
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
        monkeypatch.setattr(cli, "CLI", cli_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_pre_actions", run_pre_actions_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "should_subscribe", should_subscribe_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(main, "rollback_changes", rollback_changes_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert cli_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_pre_actions_mock.call_count == 1
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

    def test_main_rollback_pre_ponr_changes_phase(self, monkeypatch, tmp_path, global_tool_opts):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        cli_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_pre_actions_mock = mock.Mock()
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
        monkeypatch.setattr(cli, "CLI", cli_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_pre_actions", run_pre_actions_mock)
        monkeypatch.setattr(report, "_summary", report_summary_mock)
        monkeypatch.setattr(actions, "find_actions_of_severity", find_actions_of_severity_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "should_subscribe", should_subscribe_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(main, "rollback_changes", rollback_changes_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)

        assert main.main() == 2
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert cli_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_pre_actions_mock.call_count == 1
        assert report_summary_mock.call_count == 1
        assert find_actions_of_severity_mock.call_count == 1
        assert clear_versionlock_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert should_subscribe_mock.call_count == 1
        assert update_rhsm_custom_facts_mock.call_count == 1
        assert rollback_changes_mock.call_count == 1
        assert summary_as_json_mock.call_count == 1
        assert summary_as_txt_mock.call_count == 1

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
            (cli, "CLI", mock.Mock()),
            (main, "show_eula", mock.Mock()),
            (breadcrumbs, "print_data_collection", mock.Mock()),
            (system_info, "resolve_system_info", mock.Mock()),
            (system_info, "print_system_information", mock.Mock()),
            (breadcrumbs, "collect_early_data", mock.Mock()),
            (pkghandler, "clear_versionlock", mock.Mock()),
            (pkgmanager, "clean_yum_metadata", mock.Mock()),
            (actions, "run_pre_actions", mock.Mock()),
            (report, "_summary", mock.Mock()),
            (breadcrumbs, "finish_collection", mock.Mock()),
            (subscription, "should_subscribe", mock.Mock(side_effect=lambda: True)),
            (subscription, "update_rhsm_custom_facts", mock.Mock()),
            (main, "rollback_changes", mock.Mock()),
            (report, "summary_as_json", mock.Mock()),
            (report, "summary_as_txt", mock.Mock()),
            (actions, "find_actions_of_severity", mock.Mock(return_value=[])),
        )
        global_tool_opts.activity = "analysis"
        for module, function, value in mocks:
            monkeypatch.setattr(module, function, value)

        assert main.main() == 0
        assert utils.require_root.call_count == 1
        assert cli.CLI.call_count == 1
        assert main.show_eula.call_count == 1
        assert breadcrumbs.print_data_collection.call_count == 1
        assert system_info.resolve_system_info.call_count == 1
        assert system_info.print_system_information.call_count == 1
        assert breadcrumbs.collect_early_data.call_count == 1
        assert pkghandler.clear_versionlock.call_count == 1
        assert pkgmanager.clean_yum_metadata.call_count == 1
        assert actions.run_pre_actions.call_count == 1
        assert report._summary.call_count == 1
        assert breadcrumbs.finish_collection.call_count == 1
        assert subscription.should_subscribe.call_count == 1
        assert subscription.update_rhsm_custom_facts.call_count == 0
        assert main.rollback_changes.call_count == 1
        assert report.summary_as_json.call_count == 1
        assert report.summary_as_txt.call_count == 1

    def test_main_rollback_analyze_exit_phase(self, global_tool_opts, monkeypatch, tmp_path):
        require_root_mock = mock.Mock()
        initialize_file_logging_mock = mock.Mock()
        cli_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_pre_actions_mock = mock.Mock()
        report_summary_mock = mock.Mock()
        clear_versionlock_mock = mock.Mock()
        summary_as_json_mock = mock.Mock()
        summary_as_txt_mock = mock.Mock()
        find_actions_of_severity = mock.Mock(return_value=[])

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()
        should_subscribe_mock = mock.Mock(side_effect=lambda: False)
        update_rhsm_custom_facts_mock = mock.Mock()
        rollback_changes_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(cli, "CLI", cli_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_pre_actions", run_pre_actions_mock)
        monkeypatch.setattr(report, "_summary", report_summary_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "should_subscribe", should_subscribe_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(main, "rollback_changes", rollback_changes_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)
        monkeypatch.setattr(actions, "find_actions_of_severity", find_actions_of_severity)
        global_tool_opts.activity = "analysis"

        assert main.main() == 0
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert cli_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_pre_actions_mock.call_count == 1
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
        cli_cli_mock = mock.Mock()
        show_eula_mock = mock.Mock()
        print_data_collection_mock = mock.Mock()
        resolve_system_info_mock = mock.Mock()
        print_system_information_mock = mock.Mock()
        collect_early_data_mock = mock.Mock()
        clean_yum_metadata_mock = mock.Mock()
        run_pre_actions_mock = mock.Mock()
        run_post_actions_mock = mock.Mock(side_effect=Exception)
        find_actions_of_severity_mock = mock.Mock(return_value=[])
        report_summary_mock = mock.Mock()
        clear_versionlock_mock = mock.Mock()
        ask_to_continue_mock = mock.Mock()
        summary_as_json_mock = mock.Mock()
        summary_as_txt_mock = mock.Mock()
        pick_conversion_results_mock = mock.Mock(return_value=["test"])

        # Mock the rollback calls
        finish_collection_mock = mock.Mock()
        update_rhsm_custom_facts_mock = mock.Mock()

        monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
        monkeypatch.setattr(utils, "require_root", require_root_mock)
        monkeypatch.setattr(main, "initialize_file_logging", initialize_file_logging_mock)
        monkeypatch.setattr(cli, "CLI", cli_cli_mock)
        monkeypatch.setattr(main, "show_eula", show_eula_mock)
        monkeypatch.setattr(breadcrumbs, "print_data_collection", print_data_collection_mock)
        monkeypatch.setattr(system_info, "resolve_system_info", resolve_system_info_mock)
        monkeypatch.setattr(system_info, "print_system_information", print_system_information_mock)
        monkeypatch.setattr(breadcrumbs, "collect_early_data", collect_early_data_mock)
        monkeypatch.setattr(pkghandler, "clear_versionlock", clear_versionlock_mock)
        monkeypatch.setattr(pkgmanager, "clean_yum_metadata", clean_yum_metadata_mock)
        monkeypatch.setattr(actions, "run_pre_actions", run_pre_actions_mock)
        monkeypatch.setattr(actions, "run_post_actions", run_post_actions_mock)
        monkeypatch.setattr(actions, "find_actions_of_severity", find_actions_of_severity_mock)
        monkeypatch.setattr(report, "_summary", report_summary_mock)
        monkeypatch.setattr(utils, "ask_to_continue", ask_to_continue_mock)
        monkeypatch.setattr(breadcrumbs, "finish_collection", finish_collection_mock)
        monkeypatch.setattr(subscription, "update_rhsm_custom_facts", update_rhsm_custom_facts_mock)
        monkeypatch.setattr(report, "summary_as_json", summary_as_json_mock)
        monkeypatch.setattr(report, "summary_as_txt", summary_as_txt_mock)
        monkeypatch.setattr(main, "_pick_conversion_results", pick_conversion_results_mock)

        assert main.main() == 1
        assert require_root_mock.call_count == 1
        assert initialize_file_logging_mock.call_count == 1
        assert cli_cli_mock.call_count == 1
        assert show_eula_mock.call_count == 1
        assert print_data_collection_mock.call_count == 1
        assert resolve_system_info_mock.call_count == 1
        assert collect_early_data_mock.call_count == 1
        assert clean_yum_metadata_mock.call_count == 1
        assert run_pre_actions_mock.call_count == 1
        assert find_actions_of_severity_mock.call_count == 1
        assert clear_versionlock_mock.call_count == 1
        assert report_summary_mock.call_count == 2
        assert ask_to_continue_mock.call_count == 1
        assert finish_collection_mock.call_count == 1
        assert summary_as_json_mock.call_count == 1
        assert summary_as_txt_mock.call_count == 1
        assert "The system is left in an undetermined state that Convert2RHEL cannot fix." in caplog.records[-3].message
        assert update_rhsm_custom_facts_mock.call_count == 1

    @pytest.mark.parametrize(
        ("activity", "inhibitor", "rc"),
        (
            ("analysis", True, 2),
            ("analysis", False, 0),
            ("convert", True, 2),
            ("convert", False, 0),
        ),
    )
    def test_main_inhibitor_return_code(self, monkeypatch, activity, inhibitor, rc, tmp_path, global_tool_opts):
        mocks = (
            (applock, "_DEFAULT_LOCK_DIR", str(tmp_path)),
            (utils, "require_root", mock.Mock()),
            (main, "initialize_file_logging", mock.Mock()),
            (cli, "CLI", mock.Mock()),
            (main, "show_eula", mock.Mock()),
            (breadcrumbs, "print_data_collection", mock.Mock()),
            (system_info, "resolve_system_info", mock.Mock()),
            (system_info, "print_system_information", mock.Mock()),
            (breadcrumbs, "collect_early_data", mock.Mock()),
            (pkghandler, "clear_versionlock", mock.Mock()),
            (pkgmanager, "clean_yum_metadata", mock.Mock()),
            (actions, "run_pre_actions", mock.Mock()),
            (actions, "find_actions_of_severity", mock.Mock(return_value=inhibitor)),
            (report, "_summary", mock.Mock()),
            (breadcrumbs, "finish_collection", mock.Mock()),
            (subscription, "should_subscribe", mock.Mock(side_effect=lambda: True)),
            (subscription, "update_rhsm_custom_facts", mock.Mock()),
            (main, "rollback_changes", mock.Mock()),
            (report, "summary_as_json", mock.Mock()),
            (report, "summary_as_txt", mock.Mock()),
            (utils, "ask_to_continue", mock.Mock()),
            (actions, "run_post_actions", mock.Mock()),
            (utils, "restart_system", mock.Mock()),
        )
        global_tool_opts.activity = activity
        for module, function, value in mocks:
            monkeypatch.setattr(module, function, value)

        assert main.main() == rc


@pytest.mark.parametrize(
    ("data", "exception", "match", "activity"),
    (
        (
            {
                "One": {
                    "messages": [],
                    "result": {
                        "level": actions.STATUS_CODE["ERROR"],
                        "id": "ERROR_ID",
                        "title": "Error",
                        "description": "Action error",
                        "diagnosis": "User error",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            main._InhibitorsFound,
            (
                "The analysis process failed.\n\n"
                "A problem was encountered during analysis and a rollback will be "
                "initiated to restore the system as the previous state."
            ),
            "analysis",
        ),
        (
            {
                "One": {
                    "messages": [],
                    "result": {
                        "level": actions.STATUS_CODE["SKIP"],
                        "id": "SKIP_ID",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            main._InhibitorsFound,
            (
                "The analysis process failed.\n\n"
                "A problem was encountered during analysis and a rollback will be "
                "initiated to restore the system as the previous state."
            ),
            "analysis",
        ),
        (
            {
                "One": {
                    "messages": [],
                    "result": {
                        "level": actions.STATUS_CODE["SKIP"],
                        "id": "SKIP_ID",
                        "title": "Skip",
                        "description": "Action skip",
                        "diagnosis": "User skip",
                        "remediations": "move on",
                        "variables": {},
                    },
                },
            },
            main._InhibitorsFound,
            (
                "The conversion process failed.\n\n"
                "A problem was encountered during conversion and a rollback will be "
                "initiated to restore the system as the previous state."
            ),
            "conversion",
        ),
    ),
)
def test_raise_for_skipped_failures(data, exception, match, activity, global_tool_opts, monkeypatch):
    monkeypatch.setattr(toolopts, "tool_opts", global_tool_opts)
    global_tool_opts.activity = activity
    with pytest.raises(exception, match=match):
        main._raise_for_skipped_failures(data)


def test_main_already_running_conversion(monkeypatch, caplog, tmpdir):
    monkeypatch.setattr(cli, "CLI", mock.Mock())
    monkeypatch.setattr(utils, "require_root", mock.Mock())
    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmpdir))
    monkeypatch.setattr(main, "main_locked", mock.Mock(side_effect=applock.ApplicationLockedError("failed")))

    assert main.main() == 1
    assert "Another copy of convert2rhel is running.\n" in caplog.records[-2].message
    assert "\nNo changes were made to the system.\n" in caplog.records[-1].message


@pytest.mark.parametrize(("rollback_failures", "return_code"), ((["test-fail"], 1), ([], 2)))
def test_handle_inhibitors_found_exception(monkeypatch, rollback_failures, return_code, global_backup_control):
    monkeypatch.setattr(global_backup_control, "_rollback_failures", rollback_failures)

    ret = main._handle_inhibitors_found_exception()

    assert ret == return_code
