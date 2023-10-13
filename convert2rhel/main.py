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

import logging
import os
import sys

from convert2rhel import actions, applock, backup, breadcrumbs, checks, exceptions, grub
from convert2rhel import logger as logger_module
from convert2rhel import pkghandler, pkgmanager, redhatrelease, repo, subscription, systeminfo, toolopts, utils
from convert2rhel.actions import level_for_raw_action_data, report


loggerinst = logging.getLogger(__name__)


class _AnalyzeExit(Exception):
    # Exception just to exit when Analyzing
    pass


class ConversionPhase:
    POST_CLI = 1
    # PONR means Point Of No Return
    PRE_PONR_CHANGES = 2
    # Phase to exit the Analyze SubCommand early
    ANALYZE_EXIT = 3
    POST_PONR_CHANGES = 4


def initialize_logger(log_name, log_dir):
    """
    Entrypoint function that aggregates other calls for initialization logic
    and setup for logger handlers.

    .. warning::
        Setting log_dir underneath a world-writable directory (including
        letting it be user settable) is insecure.  We will need to write
        some checks for all calls to `os.makedirs()` if we allow changing
        log_dir.
    """

    try:
        logger_module.archive_old_logger_files(log_name, log_dir)
    except (IOError, OSError) as e:
        print("Warning: Unable to archive previous log: %s" % e)

    logger_module.setup_logger_handler(log_name, log_dir)


def main():
    """
    Wrapper around the main entrypoint.

    Performs everything necessary to set up before starting the actual
    conversion process itself, then calls main_locked(), protected by
    the application lock, to do the conversion process.
    """

    # Make sure we're being run by root
    utils.require_root()

    # initialize logging
    initialize_logger("convert2rhel.log", logger_module.LOG_DIR)

    # handle command line arguments
    toolopts.CLI()

    try:
        with applock.ApplicationLock("convert2rhel"):
            return main_locked()
    except applock.ApplicationLockedError:
        # We have not rotated the log files at this point because main.initialize_logger()
        # has not yet been called.  So we use sys.stderr.write() instead of loggerinst.error()
        sys.stderr.write("Another copy of convert2rhel is running.\n")
        sys.stderr.write("\nNo changes were made to the system.\n")
        return 1


def main_locked():
    """Perform all steps for the entire conversion process."""

    pre_conversion_results = None
    process_phase = ConversionPhase.POST_CLI
    try:
        perform_boilerplate()

        gather_system_info()
        prepare_system()

        # Note: set pre_conversion_results before changing to the next phase so
        # we don't fail in case rollback is triggered during
        # actions.run_actions() (either from a bug or from the user hitting
        # Ctrl-C)
        process_phase = ConversionPhase.PRE_PONR_CHANGES
        pre_conversion_results = actions.run_actions()

        if toolopts.tool_opts.activity == "analysis":
            process_phase = ConversionPhase.ANALYZE_EXIT
            raise _AnalyzeExit()

        pre_conversion_failures = actions.find_actions_of_severity(
            pre_conversion_results, "SKIP", level_for_raw_action_data
        )
        if pre_conversion_failures:
            # The report will be handled in the error handler, after rollback.
            loggerinst.critical("Conversion failed.")

        # Print the assessment just before we ask the user whether to continue past the PONR
        report.summary(
            pre_conversion_results,
            include_all_reports=False,
            disable_colors=logger_module.should_disable_color_output(),
        )

        loggerinst.warning("********************************************************")
        loggerinst.warning("The tool allows rollback of any action until this point.")
        loggerinst.warning(
            "By continuing all further changes on the system"
            " will need to be reverted manually by the user,"
            " if necessary."
        )
        loggerinst.warning("********************************************************")
        utils.ask_to_continue()

        process_phase = ConversionPhase.POST_PONR_CHANGES
        post_ponr_changes()
        loggerinst.info("\nConversion successful!\n")

        # restart system if required
        utils.restart_system()

    except _AnalyzeExit:
        breadcrumbs.breadcrumbs.finish_collection(success=True)

        rollback_changes()

        report.summary(
            pre_conversion_results,
            include_all_reports=True,
            disable_colors=logger_module.should_disable_color_output(),
        )
        return 0

    except exceptions.CriticalError as err:
        loggerinst.critical_no_exit(err.diagnosis)
        return _handle_main_exceptions(process_phase, pre_conversion_results)

    except (Exception, SystemExit, KeyboardInterrupt) as err:
        return _handle_main_exceptions(process_phase, pre_conversion_results)

    finally:
        # Write the assessment to a file as json data so that other tools can
        # parse and act upon it.
        if pre_conversion_results:
            actions.report.summary_as_json(pre_conversion_results)
            actions.report.summary_as_txt(pre_conversion_results)

    return 0


def _handle_main_exceptions(process_phase, pre_conversion_results=None):
    """Common steps to handle graceful exit due to several different Exception types."""
    breadcrumbs.breadcrumbs.finish_collection()

    no_changes_msg = "No changes were made to the system."
    utils.log_traceback(toolopts.tool_opts.debug)

    if process_phase == ConversionPhase.POST_CLI:
        loggerinst.info(no_changes_msg)
    elif process_phase == ConversionPhase.PRE_PONR_CHANGES:
        rollback_changes()
        if pre_conversion_results is None:
            loggerinst.info("\nConversion interrupted before analysis of system completed. Report not generated.\n")
        else:
            report.summary(
                pre_conversion_results,
                include_all_reports=(toolopts.tool_opts.activity == "analysis"),
                disable_colors=logger_module.should_disable_color_output(),
            )
    elif process_phase == ConversionPhase.POST_PONR_CHANGES:
        # After the process of subscription is done and the mass update of
        # packages is started convert2rhel will not be able to guarantee a
        # system rollback without user intervention. If a proper rollback
        # solution is necessary it will need to be future implemented here
        # or with the use of other backup tools.
        loggerinst.warning(
            "The conversion process failed.\n\n"
            "The system is left in an undetermined state that Convert2RHEL cannot fix. The system might not be"
            " fully converted, and might incorrectly be reporting as a Red Hat Enterprise Linux machine.\n\n"
            "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore"
            " the system from a backup."
        )
        subscription.update_rhsm_custom_facts()
    return 1


#
# Boilerplate Tasks
#


def perform_boilerplate():
    """Standard interactions with the user prior to doing any conversion work."""
    # license agreement
    loggerinst.task("Prepare: Show Red Hat software EULA")
    show_eula()

    # Telemetry opt-out
    loggerinst.task("Prepare: Inform about telemetry")
    breadcrumbs.breadcrumbs.print_data_collection()


def show_eula():
    """Print out the content of the Red Hat End User License Agreement."""

    eula_filepath = os.path.join(utils.DATA_DIR, "GLOBAL_EULA_RHEL")
    eula_text = utils.get_file_content(eula_filepath)
    if eula_text:
        loggerinst.info(eula_text)
    else:
        loggerinst.critical("EULA file not found.")
    return


#
# Preparing the System
#


def gather_system_info():
    """Retrieve information about the system to be converted"""
    # gather system information
    loggerinst.task("Prepare: Gather system information")
    systeminfo.system_info.resolve_system_info()
    systeminfo.system_info.print_system_information()
    breadcrumbs.breadcrumbs.collect_early_data()


def prepare_system():
    """Setup the environment to do the conversion within"""
    loggerinst.task("Prepare: Clear YUM/DNF version locks")
    pkghandler.clear_versionlock()

    loggerinst.task("Prepare: Clean yum cache metadata")
    pkgmanager.clean_yum_metadata()


#
# Running the conversion
#


def post_ponr_changes():
    """Start the conversion itself"""
    loggerinst.info("Starting Conversion")
    post_ponr_conversion()

    loggerinst.task("Final: Show RPM files modified by the conversion")
    systeminfo.system_info.modified_rpm_files_diff()

    loggerinst.task("Final: Update GRUB2 configuration")
    grub.update_grub_after_conversion()

    loggerinst.task("Final: Remove temporary folder %s" % utils.TMP_DIR)
    utils.remove_tmp_dir()

    loggerinst.task("Final: Check kernel boot files")
    checks.check_kernel_boot_files()

    breadcrumbs.breadcrumbs.finish_collection(success=True)

    loggerinst.task("Final: Update RHSM custom facts")
    subscription.update_rhsm_custom_facts()


def post_ponr_conversion():
    """Perform main steps for system conversion."""
    transaction_handler = pkgmanager.create_transaction_handler()
    loggerinst.task("Convert: Replace system packages")
    transaction_handler.run_transaction()
    loggerinst.task("Convert: Prepare kernel")
    pkghandler.preserve_only_rhel_kernel()
    loggerinst.task("Convert: List remaining non-Red Hat packages")
    pkghandler.list_non_red_hat_pkgs_left()
    loggerinst.task("Convert: Configure the bootloader")
    grub.post_ponr_set_efi_configuration()
    loggerinst.task("Convert: Patch yum configuration file")
    redhatrelease.YumConf().patch()
    loggerinst.task("Convert: Lock releasever in RHEL repositories")
    subscription.lock_releasever_in_rhel_repositories()


#
# Cleanup and exit
#


def rollback_changes():
    """Perform a rollback of changes made during conversion."""

    loggerinst.warning("Abnormal exit! Performing rollback ...")

    # The next section is part of a hack for 1.4 that lets us rollback some of
    # the changes registered with backup_control, do the manual, unported
    # portions of rollback, and then finish whatever is left in backup_control
    # afterwards.
    if backup.backup_control.partition not in backup.backup_control._restorables:
        backup.backup_control.push(backup.backup_control.partition)

    backup_control_was_empty = False
    try:
        backup.backup_control.pop_to_partition()
    except IndexError:
        backup_control_was_empty = True

    backup.changed_pkgs_control.restore_pkgs()
    repo.restore_varsdir()
    repo.restore_yum_repos()
    redhatrelease.system_release_file.restore()
    redhatrelease.os_release_file.restore()
    pkghandler.versionlock_file.restore()

    try:
        backup.backup_control.pop_all()
    except IndexError as e:
        if e.args[0] == "No backups to restore":
            # We have to check if we were able to pop some backups at the top
            # of this function
            if backup_control_was_empty:
                loggerinst.info("During rollback there were no backups to restore")
        else:
            raise
