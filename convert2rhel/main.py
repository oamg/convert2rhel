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

import logging
import os

from convert2rhel import actions, backup, breadcrumbs, cert, checks, grub
from convert2rhel import logger as logger_module
from convert2rhel import pkghandler, pkgmanager, redhatrelease, repo, subscription, systeminfo, toolopts, utils


loggerinst = logging.getLogger(__name__)


class ConversionPhase(object):
    INIT = 0
    POST_CLI = 1
    # PONR means Point Of No Return
    PRE_PONR_CHANGES = 2
    POST_PONR_CHANGES = 3


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
    """Perform all steps for the entire conversion process."""

    # the tool will not run if not executed under the root user
    utils.require_root()

    process_phase = ConversionPhase.INIT

    # initialize logging
    initialize_logger("convert2rhel.log", logger_module.LOG_DIR)

    # handle command line arguments
    toolopts.CLI()
    try:
        process_phase = ConversionPhase.POST_CLI
        perform_boilerplate()

        gather_system_info()
        prepare_system()

        ### FIXME: This should be expected to either succeed or fail.  Need to look for the return
        ### value and act upon it.
        system_checks()

        ### FIXME: After talking with mbocek, let's merge this in with the actions framework
        pre_ponr_changes()

        # if toolopts.tool_opts.command == "analyze":
        #     rollback()
        #     # Return code here depends on the result of the action framework.
        #     return 0

        post_ponr_changes()

        ### Port the code below into pre_ponr_changes(), rollback(), or post_ponr_changes().

        # backup system release file before starting conversion process
        loggerinst.task("Prepare: Backup System")
        redhatrelease.system_release_file.backup()
        redhatrelease.os_release_file.backup()
        repo.backup_yum_repos()
        repo.backup_varsdir()

        ### End calls that should be put into pre_ponr_changes(), rollback(), or post_ponr_changes()

        # begin conversion process
        process_phase = ConversionPhase.PRE_PONR_CHANGES
        # pre_ponr_conversion()

        if os.getenv("CONVERT2RHEL_EXPERIMENTAL_ANALYSIS", None):
            # TODO: Include report before rollback
            rollback()

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

        loggerinst.info("\nConversion successful!\n")

        # restart system if required
        utils.restart_system()

    except (Exception, SystemExit, KeyboardInterrupt) as err:
        # Catching the three exception types separately due to python 2.4
        # (RHEL 5) - 2.7 (RHEL 7) compatibility.
        utils.log_traceback(toolopts.tool_opts.debug)
        no_changes_msg = "No changes were made to the system."
        breadcrumbs.breadcrumbs.finish_collection(success=False)

        if is_help_msg_exit(process_phase, err):
            return 0
        elif process_phase == ConversionPhase.INIT:
            print(no_changes_msg)
        elif process_phase == ConversionPhase.POST_CLI:
            loggerinst.info(no_changes_msg)
        elif process_phase == ConversionPhase.PRE_PONR_CHANGES:
            rollback_changes()
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
    return 0


#
# Boilerplate Task
#


def perform_boilerplate():
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
# Gathering system information
#


def gather_system_info():
    # gather system information
    loggerinst.task("Prepare: Gather system information")
    systeminfo.system_info.resolve_system_info()
    systeminfo.system_info.print_system_information()
    breadcrumbs.breadcrumbs.collect_early_data()


def prepare_system():
    loggerinst.task("Prepare: Clear YUM/DNF version locks")
    pkghandler.clear_versionlock()

    loggerinst.task("Prepare: Clean yum cache metadata")
    pkgmanager.clean_yum_metadata()


def system_checks():
    # check the system prior the conversion (possible inhibit)
    pass


def pre_ponr_changes():
    pass


def pre_ponr_checks():
    pass


def post_ponr_changes():
    pass


def rollback():
    pass


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
    return


def is_help_msg_exit(process_phase, err):
    """After printing the help message, optparse within the toolopts.CLI()
    call terminates the process with sys.exit(0).
    """
    if process_phase == ConversionPhase.INIT and isinstance(err, SystemExit) and err.args[0] == 0:
        return True
    return False


def rollback_changes():
    """Perform a rollback of changes made during conversion."""

    loggerinst.warning("Abnormal exit! Performing rollback ...")
    subscription.rollback()
    backup.changed_pkgs_control.restore_pkgs()
    repo.restore_varsdir()
    repo.restore_yum_repos()
    redhatrelease.system_release_file.restore()
    redhatrelease.os_release_file.restore()
    pkghandler.versionlock_file.restore()
    system_cert = cert.SystemCert()
    system_cert.remove()
    try:
        backup.backup_control.pop_all()
    except IndexError as e:
        if e.args[0] == "No backups to restore":
            loggerinst.info("During rollback there were no backups to restore")
        else:
            raise

    return
