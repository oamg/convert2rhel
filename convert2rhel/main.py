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
import sys

from convert2rhel import logger
from convert2rhel import pkghandler
from convert2rhel import redhatrelease
from convert2rhel import repo
from convert2rhel import rhelvariant
from convert2rhel import subscription
from convert2rhel import systeminfo
from convert2rhel import toolopts
from convert2rhel import utils


class ConversionPhase(object):
    INIT = 0
    POST_CLI = 1
    # PONR means Point Of No Return
    PRE_PONR_CHANGES = 2
    POST_PONR_CHANGES = 3


def main():
    """Perform all steps for the entire conversion process."""

    # the tool will not run if not executed under the root user
    utils.require_root()

    process_phase = ConversionPhase.INIT
    # initialize logging
    logger.initialize_logger("convert2rhel.log")
    # get module level logger (inherits from root logger)
    loggerinst = logging.getLogger(__name__)

    try:
        # handle command line arguments
        toolopts.CLI()

        process_phase = ConversionPhase.POST_CLI

        # license agreement
        loggerinst.task("Prepare: End user license agreement")
        user_to_accept_eula()

        # gather system information
        loggerinst.task("Prepare: Gather system information")
        systeminfo.system_info.resolve_system_info()
        loggerinst.task("Prepare: Determine RHEL variant")
        rhelvariant.determine_rhel_variant()

        # backup system release file before starting conversion process
        loggerinst.task("Prepare: Backup System")
        redhatrelease.system_release_file.backup()
        redhatrelease.yum_conf.backup()

        loggerinst.task("Prepare: Clear YUM/DNF version locks")
        pkghandler.clear_versionlock()

        # begin conversion process
        process_phase = ConversionPhase.PRE_PONR_CHANGES
        pre_ponr_conversion()

        loggerinst.warning("The tool allows rollback of any action until this"
                           " point.")
        loggerinst.warning("By continuing all further changes on the system"
                           " will need to be reverted manually by the user,"
                           " if necessary.")
        utils.ask_to_continue()

        process_phase = ConversionPhase.POST_PONR_CHANGES
        post_ponr_conversion()

        loggerinst.task("Final: rpm files modified by the conversion")
        systeminfo.system_info.modified_rpm_files_diff()

        # recommend non-interactive command
        loggerinst.task("Final: Non-interactive mode")
        toolopts.print_non_interactive_opts()

        # restart system if required
        utils.restart_system()

    except (Exception, SystemExit, KeyboardInterrupt) as err:
        # Catching the three exception types separately due to python 2.4
        # (RHEL 5) - 2.7 (RHEL 7) compatibility.

        utils.log_traceback(toolopts.tool_opts.debug)
        no_changes_msg = "No changes were made to the system."

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
            loggerinst.warning("Conversion process interrupted and manual user intervention will be necessary.")

        return 1

    return 0


def user_to_accept_eula():
    """Request user to accept EULA license agreement. This is required
    otherwise the conversion process stops and fails with error.
    """
    loggerinst = logging.getLogger(__name__)

    eula_filename = "GLOBAL_EULA_RHEL"
    eula_filepath = os.path.join(utils.DATA_DIR, eula_filename)
    eula_text = utils.get_file_content(eula_filepath)
    if eula_text:
        loggerinst.info(eula_text)
        loggerinst.warning("By continuing you accept this EULA.")
        utils.ask_to_continue()
    else:
        loggerinst.critical('EULA file not found.')
    return


def pre_ponr_conversion():
    """Perform steps and checks to guarantee system is ready for conversion."""
    loggerinst = logging.getLogger(__name__)

    # remove excluded packages
    loggerinst.task("Convert: Remove excluded packages")
    pkghandler.remove_excluded_pkgs()

    # install redhat release package
    loggerinst.task("Convert: Install Red Hat release package")
    redhatrelease.install_release_pkg()
    # replace distroverpkg variable in yum.conf
    loggerinst.task("Convert: Patch yum configuration file")
    redhatrelease.YumConf().patch()

    # package analysis
    loggerinst.task("Convert: List third-party packages")
    pkghandler.list_third_party_pkgs()
    if not toolopts.tool_opts.disable_submgr:
        loggerinst.task("Convert: Subscription Manager - Install")
        subscription.install_subscription_manager()
        loggerinst.task("Convert: Subscription Manager - Subscribe system")
        subscription.subscribe_system()
        loggerinst.task("Convert: Get RHEL repository IDs")
        rhel_repoids = repo.get_rhel_repoids()
        loggerinst.task("Convert: Subscription Manager - Check required repositories")
        subscription.check_needed_repos_availability(rhel_repoids)
        loggerinst.task("Convert: Subscription Manager - Disable all repositories")
        subscription.disable_repos()
        loggerinst.task("Convert: Subscription Manager - Enable RHEL repositories")
        subscription.enable_repos(rhel_repoids)
        # TODO: Replace renaming .repo files by using --enable for yum command
        loggerinst.task("Convert: Subscription Manager - Rename repositories")
        subscription.rename_repo_files()


def post_ponr_conversion():
    """Perform main steps for system conversion."""
    loggerinst = logging.getLogger(__name__)

    loggerinst.task("Convert: Import Red Hat GPG keys")
    pkghandler.install_gpg_keys()
    loggerinst.task("Convert: Prepare kernel")
    pkghandler.preserve_only_rhel_kernel()
    loggerinst.task("Convert: Replace packages")
    pkghandler.replace_non_red_hat_packages()
    loggerinst.task("Convert: List remaining non-Red Hat packages")
    pkghandler.list_non_red_hat_pkgs_left()
    return


def is_help_msg_exit(process_phase, err):
    """After printing the help message, optparse within the toolopts.CLI()
    call terminates the process with sys.exit(0).
    """
    if process_phase == ConversionPhase.INIT and \
            isinstance(err, SystemExit) and err.args[0] == 0:
        return True
    return False


def rollback_changes():
    """Perform a rollback of changes made during conversion."""
    loggerinst = logging.getLogger(__name__)

    loggerinst.warn("Abnormal exit! Performing rollback ...")
    subscription.rollback()
    utils.changed_pkgs_control.restore_pkgs()
    redhatrelease.system_release_file.restore()
    redhatrelease.yum_conf.restore()
    pkghandler.versionlock_file.restore()

    return


if __name__ == "__main__":
    sys.exit(main())
