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

from convert2rhel import (
    cert,
    checks,
    logger,
    pkghandler,
    redhatrelease,
    repo,
    special_cases,
    subscription,
    systeminfo,
    toolopts,
    utils,
)


loggerinst = logging.getLogger(__name__)


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

    # handle command line arguments
    toolopts.CLI()

    try:
        process_phase = ConversionPhase.POST_CLI

        # license agreement
        loggerinst.task("Prepare: Show Red Hat software EULA")
        show_eula()

        # gather system information
        loggerinst.task("Prepare: Gather system information")
        systeminfo.system_info.resolve_system_info()

        # check the system prior the conversion (possible inhibit)
        loggerinst.task("Prepare: Initial system checks before conversion")
        checks.perform_pre_checks()

        # backup system release file before starting conversion process
        loggerinst.task("Prepare: Backup System")
        redhatrelease.system_release_file.backup()
        redhatrelease.yum_conf.backup()
        repo.backup_yum_repos()

        loggerinst.task("Prepare: Clear YUM/DNF version locks")
        pkghandler.clear_versionlock()

        # begin conversion process
        process_phase = ConversionPhase.PRE_PONR_CHANGES
        pre_ponr_conversion()

        loggerinst.warning("********************************************************")
        loggerinst.warning("The tool allows rollback of any action until this point.")
        loggerinst.warning("By continuing all further changes on the system"
                           " will need to be reverted manually by the user,"
                           " if necessary.")
        loggerinst.warning("********************************************************")
        utils.ask_to_continue()

        process_phase = ConversionPhase.POST_PONR_CHANGES
        post_ponr_conversion()

        loggerinst.task("Final: rpm files modified by the conversion")
        systeminfo.system_info.modified_rpm_files_diff()

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


def show_eula():
    """Print out the content of the Red Hat End User License Agreement."""

    eula_filepath = os.path.join(utils.DATA_DIR, "GLOBAL_EULA_RHEL")
    eula_text = utils.get_file_content(eula_filepath)
    if eula_text:
        loggerinst.info(eula_text)
    else:
        loggerinst.critical('EULA file not found.')
    return


def pre_ponr_conversion():
    """Perform steps and checks to guarantee system is ready for conversion."""

    # check if user pass some repo to both disablerepo and enablerepo options
    pkghandler.has_duplicate_repos_across_disablerepo_enablerepo_options()

    # package analysis
    loggerinst.task("Convert: List third-party packages")
    pkghandler.list_third_party_pkgs()

    # remove excluded packages
    loggerinst.task("Convert: Remove excluded packages")
    pkghandler.remove_excluded_pkgs()


    # handle special cases
    loggerinst.task("Convert: Resolve possible edge cases")
    special_cases.check_and_resolve()

    rhel_repoids = []
    if not toolopts.tool_opts.disable_submgr:
        loggerinst.task("Convert: Subscription Manager - Download packages")
        subscription.download_rhsm_pkgs()
        loggerinst.task("Convert: Subscription Manager - Replace")
        subscription.replace_subscription_manager()
        loggerinst.task("Convert: Install RHEL certificates for RHSM")
        system_cert = cert.SystemCert()
        system_cert.install()
        loggerinst.task("Convert: Subscription Manager - Subscribe system")
        subscription.subscribe_system()
        loggerinst.task("Convert: Get RHEL repository IDs")
        rhel_repoids = repo.get_rhel_repoids()
        loggerinst.task("Convert: Subscription Manager - Check required repositories")
        subscription.check_needed_repos_availability(rhel_repoids)
        loggerinst.task("Convert: Subscription Manager - Disable all repositories")
        subscription.disable_repos()

    # remove non-RHEL packages containing repofiles or affecting variables in the repofiles
    loggerinst.task("Convert: Remove packages containing repofiles")
    pkghandler.remove_repofile_pkgs()

    # we need to enable repos after removing repofile pkgs, otherwise we don't get backups
    # to restore from on a rollback
    if not toolopts.tool_opts.disable_submgr:
        loggerinst.task("Convert: Subscription Manager - Enable RHEL repositories")
        subscription.enable_repos(rhel_repoids)

    # comment out the distroverpkg variable in yum.conf
    loggerinst.task("Convert: Patch yum configuration file")
    redhatrelease.YumConf().patch()

    # perform final checks before the conversion
    loggerinst.task("Convert: Final system checks before main conversion")
    checks.perform_pre_ponr_checks()


def post_ponr_conversion():
    """Perform main steps for system conversion."""

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

    loggerinst.warn("Abnormal exit! Performing rollback ...")
    subscription.rollback()
    utils.changed_pkgs_control.restore_pkgs()
    repo.restore_yum_repos()
    redhatrelease.system_release_file.restore()
    redhatrelease.yum_conf.restore()
    pkghandler.versionlock_file.restore()

    return


if __name__ == "__main__":
    sys.exit(main())
