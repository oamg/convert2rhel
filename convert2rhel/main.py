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

from convert2rhel import actions, applock, backup, breadcrumbs, cli, exceptions
from convert2rhel import logger as logger_module
from convert2rhel import pkghandler, pkgmanager, subscription, systeminfo, utils
from convert2rhel.actions import level_for_raw_action_data, report
from convert2rhel.phase import ConversionPhase, ConversionPhases  # noqa: F401 ignoring due to type comments
from convert2rhel.toolopts import tool_opts

loggerinst = logger_module.root_logger.getChild(__name__)


class _AnalyzeExit(Exception):
    # Exception just to exit when Analyzing
    pass


class _InhibitorsFound(Exception):
    # Exception for when there is an inhibitor detected either in
    # pre-conversion or post-conversion actions.
    pass


_REPORT_MAPPING = {
    ConversionPhases.ANALYZE_EXIT.name: (
        report.CONVERT2RHEL_PRE_CONVERSION_JSON_RESULTS,
        report.CONVERT2RHEL_PRE_CONVERSION_TXT_RESULTS,
    ),
    ConversionPhases.PRE_PONR_CHANGES.name: (
        report.CONVERT2RHEL_PRE_CONVERSION_JSON_RESULTS,
        report.CONVERT2RHEL_PRE_CONVERSION_TXT_RESULTS,
    ),
    ConversionPhases.POST_PONR_CHANGES.name: (
        report.CONVERT2RHEL_POST_CONVERSION_JSON_RESULTS,
        report.CONVERT2RHEL_POST_CONVERSION_TXT_RESULTS,
    ),
}


# Track the exit codes for different scenarios during the conversion.
class ConversionExitCodes:
    # No errors detected during the conversion
    SUCCESSFUL = 0
    # Some exception was raised (excluding _InhibitorsFound and _AnalyzeExit) or rollback failed
    # Internal convert2rhel problem
    FAILURE = 1
    # Inhibitors found - problem found on the system (like outdated packages, failed to subscribe etc.)
    INHIBITORS_FOUND = 2


def initialize_file_logging(log_name, log_dir):
    """
    Archive existing file logs and setup all logging handlers that require
    root, like FileHandlers.

    This function should be called after
    :func:`~convert2rhel.main.initialize_logger`.

    .. warning::
        Setting log_dir underneath a world-writable directory (including
        letting it be user settable) is insecure.  We will need to write
        some checks for all calls to `os.makedirs()` if we allow changing
        log_dir.

    :param str log_name: Name of the logfile to archive and log to
    :param str log_dir: Directory where logfiles are stored
    """
    try:
        logger_module.archive_old_logger_files(log_name, log_dir)
    except (IOError, OSError) as e:
        loggerinst.warning("Unable to archive previous log: {}".format(e))

    logger_module.add_file_handler(log_name, log_dir)


def main():
    """
    Wrapper around the main entrypoint.

    Performs everything necessary to set up before starting the actual
    conversion process itself, then calls main_locked(), protected by
    the application lock, to do the conversion process.
    """

    # handle command line arguments
    cli.CLI()

    # Make sure we're being run by root
    utils.require_root()

    try:
        with applock.ApplicationLock("convert2rhel"):
            return main_locked()
    except applock.ApplicationLockedError:
        loggerinst.warning("Another copy of convert2rhel is running.\n")
        loggerinst.warning("\nNo changes were made to the system.\n")
        return ConversionExitCodes.FAILURE


def main_locked():
    """Perform all steps for the entire conversion process."""

    pre_conversion_results = None
    post_conversion_results = None
    ConversionPhases.set_current(ConversionPhases.POST_CLI)

    # since we now have root, we can add the FileLogging
    # and also archive previous logs
    initialize_file_logging("convert2rhel.log", logger_module.LOG_DIR)

    try:
        ConversionPhases.set_current(ConversionPhases.PREPARE)
        perform_boilerplate()

        gather_system_info()
        prepare_system()

        # Note: set pre_conversion_results before changing to the next phase so
        # we don't fail in case rollback is triggered during
        # actions.run_pre_actions() (either from a bug or from the user hitting
        # Ctrl-C)
        ConversionPhases.set_current(ConversionPhases.PRE_PONR_CHANGES)
        pre_conversion_results = actions.run_pre_actions()

        if tool_opts.activity == "analysis":
            ConversionPhases.set_current(ConversionPhases.ANALYZE_EXIT)
            raise _AnalyzeExit()

        _raise_for_skipped_failures(pre_conversion_results)

        # Print the assessment just before we ask the user whether to continue past the PONR
        report.pre_conversion_report(
            results=pre_conversion_results,
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

        ConversionPhases.set_current(ConversionPhases.POST_PONR_CHANGES)
        post_conversion_results = actions.run_post_actions()

        _raise_for_skipped_failures(post_conversion_results)
        report.post_conversion_report(
            results=post_conversion_results,
            include_all_reports=True,
            disable_colors=logger_module.should_disable_color_output(),
        )

        loggerinst.info("\nConversion successful!\n")

        # restart system if required
        utils.restart_system()
    except _AnalyzeExit:
        breadcrumbs.breadcrumbs.finish_collection(success=True)
        # Update RHSM custom facts only when this returns False. Otherwise,
        # sub-man get uninstalled and the data is removed from the RHSM server.
        if not subscription.should_subscribe():
            subscription.update_rhsm_custom_facts()

        rollback_changes()
        provide_status_after_rollback(pre_conversion_results, include_all_reports=True)

        if backup.backup_control.rollback_failed:
            return ConversionExitCodes.FAILURE

        if _get_failed_actions(pre_conversion_results):
            return ConversionExitCodes.INHIBITORS_FOUND

        return ConversionExitCodes.SUCCESSFUL
    except _InhibitorsFound as err:
        loggerinst.critical_no_exit(str(err))
        results = _pick_conversion_results(pre_conversion_results, post_conversion_results)
        _handle_main_exceptions(current_phase=ConversionPhases.current_phase, results=results)

        return _handle_inhibitors_found_exception()
    except exceptions.CriticalError as err:
        loggerinst.critical_no_exit(err.diagnosis)
        results = _pick_conversion_results(pre_conversion_results, post_conversion_results)
        return _handle_main_exceptions(current_phase=ConversionPhases.current_phase, results=results)
    except (Exception, SystemExit, KeyboardInterrupt):
        results = _pick_conversion_results(pre_conversion_results, post_conversion_results)
        return _handle_main_exceptions(current_phase=ConversionPhases.current_phase, results=results)
    finally:
        if not backup.backup_control.rollback_failed:
            # Write the assessment to a file as json data so that other tools can
            # parse and act upon it.
            results = _pick_conversion_results(pre_conversion_results, post_conversion_results)
            current_phase = ConversionPhases.current_phase  # type: ConversionPhase|None

            execution_phase = current_phase

            if current_phase and current_phase == ConversionPhases.ROLLBACK:
                # Rollback is an indication of what we are doing, but here we want to know what we were doing before the
                # rollback so that we can make assertions. Hence fetching the previous stage
                execution_phase = current_phase.last_stage

            if results and execution_phase and execution_phase.name in _REPORT_MAPPING:
                json_report, txt_report = _REPORT_MAPPING[execution_phase.name]

                report.summary_as_json(results, json_report)
                report.summary_as_txt(results, txt_report)

    return ConversionExitCodes.SUCCESSFUL


def _get_failed_actions(results):
    return actions.find_actions_of_severity(results, "SKIP", level_for_raw_action_data)


def _raise_for_skipped_failures(results):
    """Analyze the action results for failures

    :param results: The action results from the framework
    :type results: dict
    :raises SystemExit: In case we detect any actions that has level of `SKIP`
        or above.
    """
    failures = _get_failed_actions(results)
    if failures:
        # The report will be handled in the error handler, after rollback.
        message = (
            "The {method} process failed.\n\n"
            "A problem was encountered during {method} and a rollback will be "
            "initiated to restore the system as the previous state."
        ).format(method=tool_opts.activity)
        raise _InhibitorsFound(message)


# TODO(r0x0d): Better function name
def _pick_conversion_results(pre_conversion, post_conversion):
    """Utilitary function to define which action results to use

    Maybe not be necessary (or even correct), but it is the best approximation
    idea for now.
    """
    if ConversionPhases.current_phase == ConversionPhases.POST_PONR_CHANGES:
        return post_conversion

    return pre_conversion


def _handle_main_exceptions(current_phase, results=None):  # type: (ConversionPhase|None, dict|None) -> int
    """Common steps to handle graceful exit due to several different Exception types."""
    breadcrumbs.breadcrumbs.finish_collection()

    no_changes_msg = "No changes were made to the system."
    utils.log_traceback(tool_opts.debug)

    execution_phase = current_phase  # type: ConversionPhase|None

    if current_phase and current_phase == ConversionPhases.ROLLBACK:
        # Rollback is an indication of what we are doing, but here we want to know what we were doing before the
        # rollback so that we can make assertions. Hence fetching the previous stage
        execution_phase = current_phase.last_stage

    if execution_phase in [ConversionPhases.POST_CLI, ConversionPhases.PREPARE]:
        loggerinst.info(no_changes_msg)
        return ConversionExitCodes.FAILURE
    elif execution_phase == ConversionPhases.PRE_PONR_CHANGES:
        # Update RHSM custom facts only when this returns False. Otherwise,
        # sub-man get uninstalled and the data is removed from the RHSM server.
        if not subscription.should_subscribe():
            subscription.update_rhsm_custom_facts()

        rollback_changes()
        provide_status_after_rollback(
            pre_conversion_results=results,
            include_all_reports=True,
        )
    elif execution_phase == ConversionPhases.POST_PONR_CHANGES:
        # After the process of subscription is done and the mass update of
        # packages is started convert2rhel will not be able to guarantee a
        # system rollback without user intervention. If a proper rollback
        # solution is necessary it will need to be future implemented here
        # or with the use of other backup tools.
        subscription.update_rhsm_custom_facts()
        loggerinst.warning(
            "The conversion process failed.\n\n"
            "The system is left in an undetermined state that Convert2RHEL cannot fix. The system might not be"
            " fully converted, and might incorrectly be reporting as a Red Hat Enterprise Linux machine.\n\n"
            "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore"
            " the system from a backup."
        )

        report.post_conversion_report(
            results=results,
            include_all_reports=True,
            disable_colors=logger_module.should_disable_color_output(),
        )

    return ConversionExitCodes.FAILURE


def _handle_inhibitors_found_exception():
    """Handle return code when handling InhibitorFound exception."""
    if backup.backup_control.rollback_failed:
        return ConversionExitCodes.FAILURE

    return ConversionExitCodes.INHIBITORS_FOUND


#
# Boilerplate Tasks
#


def perform_boilerplate():
    """Standard interactions with the user prior to doing any conversion work."""
    # license agreement
    loggerinst.task("Show Red Hat software EULA")
    show_eula()

    loggerinst.task("Inform about data collection")
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
    loggerinst.task("Gather system information")
    systeminfo.system_info.resolve_system_info()
    systeminfo.system_info.print_system_information()
    breadcrumbs.breadcrumbs.collect_early_data()


def prepare_system():
    """Setup the environment to do the conversion within"""
    loggerinst.task("Clear YUM/DNF version locks")
    pkghandler.clear_versionlock()

    loggerinst.task("Clean yum cache metadata")
    pkgmanager.clean_yum_metadata()


#
# Cleanup and exit
#


def rollback_changes():
    """Perform a rollback of changes made during conversion."""

    loggerinst.warning("Abnormal exit! Performing rollback ...")
    ConversionPhases.set_current(ConversionPhases.ROLLBACK)

    try:
        backup.backup_control.pop_all()
    except IndexError as e:
        if e.args[0] == "No backups to restore":
            loggerinst.info("During rollback there were no backups to restore")
        else:
            raise

    return


def provide_status_after_rollback(pre_conversion_results, include_all_reports):
    """Print after-rollback messages and determine if there is a report to print or
    if report shouldn't be printed after failure in rollback."""
    if backup.backup_control.rollback_failed:
        loggerinst.critical_no_exit(
            "Rollback of system wasn't completed successfully.\n"
            "The system is left in an undetermined state that Convert2RHEL cannot fix.\n"
            "It is strongly recommended to store the Convert2RHEL logs for later investigation, and restore"
            " the system from a backup.\n"
            "Following errors were captured during rollback:\n"
            "{}".format("\n".join(backup.backup_control.rollback_failures))
        )

        return

    if not pre_conversion_results:
        loggerinst.info("\nConversion interrupted before analysis of system completed. Report not generated.\n")

        return

    report.pre_conversion_report(
        results=pre_conversion_results,
        include_all_reports=include_all_reports,
        disable_colors=logger_module.should_disable_color_output(),
    )
