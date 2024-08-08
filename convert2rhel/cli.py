# -*- coding: utf-8 -*-
#
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


import argparse
import logging
import os
import sys

from convert2rhel import __version__, utils
from convert2rhel.toolopts import CliConfig, FileConfig, initialize_toolopts, tool_opts


loggerinst = logging.getLogger(__name__)


# For a list of modified rpm files before the conversion starts
PRE_RPM_VA_LOG_FILENAME = "rpm_va.log"

# For a list of modified rpm files after the conversion finishes for comparison purposes
POST_RPM_VA_LOG_FILENAME = "rpm_va_after_conversion.log"

ARGS_WITH_VALUES = [
    "-u",
    "--username",
    "-p",
    "--password",
    "-k",
    "--activationkey",
    "-o",
    "--org",
    "--pool",
    "--serverurl",
]
PARENT_ARGS = ["--debug", "--help", "-h", "--version"]


class CLI:
    def __init__(self):
        self._parser = self._get_argparser()
        self._shared_options_parser = argparse.ArgumentParser(add_help=False)
        # Duplicating parent options here as we want to make it
        # available for any other basic operation that we run without a
        # subcommand in mind, and, it is a shared option so we can share it
        # between any subcommands we may create in the future.
        self._register_parent_options(self._parser)
        self._register_parent_options(self._shared_options_parser)
        self._register_options()
        self._process_cli_options()

    @staticmethod
    def usage(subcommand_to_print="<subcommand>"):
        # Override the subcommand_to_print parameter if the tool has been executed through CLI but without
        # subcommand specified. This is to make sure that runnning `convert2rhel --help` on the CLI will print the
        # usage with generic <subcommand>, while the manpage generated using argparse_manpage will be able to print the
        # usage correctly for subcommands as it does not execute convert2rhel from the CLI.
        subcommand_not_used_on_cli = "/usr/bin/convert2rhel" in sys.argv[0] and not _subcommand_used(sys.argv)
        if subcommand_not_used_on_cli:
            subcommand_to_print = "<subcommand>"
        usage = (
            "\n"
            "  convert2rhel [--version] [-h]\n"
            "  convert2rhel {subcommand} [-u username] [-p password | -c conf_file_path] [--pool pool_id | -a] [--disablerepo repoid]"
            " [--enablerepo repoid] [--serverurl url] [--no-rpm-va] [--eus] [--els] [--debug] [--restart] [-y]\n"
            "  convert2rhel {subcommand} [--no-rhsm] [--disablerepo repoid] [--enablerepo repoid] [--no-rpm-va] [--eus] [--els] [--debug] [--restart] [-y]\n"
            "  convert2rhel {subcommand} [-k activation_key | -c conf_file_path] [-o organization] [--pool pool_id | -a] [--disablerepo repoid] [--enablerepo"
            " repoid] [--serverurl url] [--no-rpm-va] [--eus] [--els] [--debug] [--restart] [-y]\n"
        ).format(subcommand=subcommand_to_print)

        if subcommand_not_used_on_cli:
            usage = usage + "\n  Subcommands: analyze, convert"
        return usage

    def _get_argparser(self):
        return argparse.ArgumentParser(conflict_handler="resolve", usage=self.usage())

    def _register_commands(self):
        """Configures parsers specific to the analyze and convert subcommands"""
        subparsers = self._parser.add_subparsers(title="Subcommands", dest="command")
        self._analyze_parser = subparsers.add_parser(
            "analyze",
            help="Run all Convert2RHEL initial checks up until the"
            " Point of no Return (PONR) and generate a report with the findings."
            " A rollback is initiated after the checks to put the system back"
            " in the original state.",
            parents=[self._shared_options_parser],
            usage=self.usage(subcommand_to_print="analyze"),
        )
        self._convert_parser = subparsers.add_parser(
            "convert",
            help="Convert the system. If no subcommand is given, 'convert' is used as a default.",
            parents=[self._shared_options_parser],
            usage=self.usage(subcommand_to_print="convert"),
        )

    @staticmethod
    def _register_parent_options(parser):
        """Prescribe what parent command line options the tool accepts."""
        parser.add_argument(
            "--version",
            action="version",
            version=__version__,
            help="Show convert2rhel version and exit.",
        )
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Print traceback in case of an abnormal exit and messages that could help find an issue.",
        )

    def _register_options(self):
        """Prescribe what command line options the tool accepts."""
        self._parser.add_argument(
            "-h",
            "--help",
            action="help",
            help="Show help message and exit.",
        )
        self._shared_options_parser.add_argument(
            "--no-rpm-va",
            action="store_true",
            help="Skip gathering changed rpm files using"
            " 'rpm -Va'. By default it's performed before and after the conversion with the output"
            " stored in log files %s and %s. At the end of the conversion, these logs are compared"
            " to show you what rpm files have been affected by the conversion."
            " Cannot be used with analyze subcommand."
            " The environment variable CONVERT2RHEL_INCOMPLETE_ROLLBACK"
            " needs to be set to 1 to use this argument." % (PRE_RPM_VA_LOG_FILENAME, POST_RPM_VA_LOG_FILENAME),
        )
        self._shared_options_parser.add_argument(
            "--eus",
            action="store_true",
            help="Explicitly recognize the system as eus, utilizing eus repos."
            " This option is meant for el8.8+ systems.",
        )
        self._shared_options_parser.add_argument(
            "--els",
            action="store_true",
            help="Explicitly recognize the system as els, utilizing els repos."
            " This option is meant for el7 systems.",
        )
        self._shared_options_parser.add_argument(
            "--enablerepo",
            metavar="repoidglob",
            action="append",
            help="Enable specific"
            " repositories by ID or glob. For more repositories to enable, use this option"
            " multiple times. If you don't use the --no-rhsm option, you can use this option"
            " to override the default RHEL repoids that convert2rhel enables through"
            " subscription-manager.",
        )
        self._shared_options_parser.add_argument(
            "--disablerepo",
            metavar="repoidglob",
            action="append",
            help="Disable specific"
            " repositories by ID or glob. For more repositories to disable, use this option"
            " multiple times. This option defaults to all repositories ('*').",
        )
        self._shared_options_parser.add_argument(
            "-r",
            "--restart",
            help="Restart the system when it is successfully converted to RHEL to boot the new RHEL kernel."
            " It has no effect when used with the 'analyze' subcommand.",
            action="store_true",
        )
        self._shared_options_parser.add_argument(
            "-y",
            help="Answer yes to all yes/no questions the tool asks.",
            dest="auto_accept",
            action="store_true",
        )
        self._add_subscription_manager_options()
        self._add_alternative_installation_options()
        self._register_commands()

    def _add_alternative_installation_options(self):
        """Prescribe what alternative command line options the tool accepts."""
        group = self._shared_options_parser.add_argument_group(
            title="Alternative Installation Options",
            description="The following options are required if you do not intend on using subscription-manager.",
        )
        group.add_argument(
            "--no-rhsm",
            action="store_true",
            help="Do not use the subscription-manager, use custom repositories instead. See --enablerepo/--disablerepo"
            " options. Without this option, the subscription-manager is used to access RHEL repositories by default."
            " Using this option requires to have the --enablerepo specified.",
        )

    def _add_subscription_manager_options(self):
        """Prescribe what subscription manager command line options the tool accepts."""
        group = self._shared_options_parser.add_argument_group(
            title="Subscription Manager Options",
            description="The following options are specific to using subscription-manager.",
        )
        group.add_argument(
            "-u",
            "--username",
            help="Username for the"
            " subscription-manager. If neither --username nor"
            " --activation-key option is used, the user"
            " is asked to enter the username.",
        )
        group.add_argument(
            "-p",
            "--password",
            help="Password for the"
            " subscription-manager. If --password, --config-file or --activationkey are not"
            " used, the user is asked to enter the password."
            " We recommend using the --config-file option instead to prevent leaking the password"
            " through a list of running processes.",
        )
        group.add_argument(
            "-k",
            "--activationkey",
            help="Activation key used"
            " for the system registration by the"
            " subscription-manager. It requires to have the --org"
            " option specified."
            " We recommend using the --config-file option instead to prevent leaking the activation key"
            " through a list of running processes.",
            dest="activation_key",
        )
        group.add_argument(
            "-o",
            "--org",
            help="Organization with which the"
            " system will be registered by the"
            " subscription-manager. A list of available"
            " organizations is possible to obtain by running"
            " 'subscription-manager orgs'. From the listed pairs"
            " Name:Key, use the Key here.",
        )
        group.add_argument(
            "-c",
            "--config-file",
            help="The configuration file is an optional way to safely pass either a user password or an activation key"
            " to the subscription-manager to register the system. This is more secure than passing these values"
            " through the --activationkey or --password option, which might leak the values"
            " through a list of running processes."
            " You can edit the pre-installed configuration file template at /etc/convert2rhel.ini or create a new"
            " configuration file at ~/.convert2rhel.ini. The convert2rhel utility loads the configuration from either"
            " of those locations, the latter having preference over the former. Alternatively, you can specify a path"
            " to the configuration file using the --config-file option to override other configurations.",
        )
        group.add_argument(
            "-a",
            "--auto-attach",
            help="Automatically attach compatible subscriptions to the system.",
            action="store_true",
        )
        group.add_argument(
            "--pool",
            help="Subscription pool ID. A list of the available"
            " subscriptions is possible to obtain by running"
            " 'subscription-manager list --available'."
            " If no pool ID is provided, the --auto option is used",
        )
        group.add_argument(
            "--serverurl",
            help="Hostname of the subscription service to be used when registering the system with"
            " subscription-manager. The default is the Customer Portal Subscription Management service"
            " (subscription.rhsm.redhat.com). It is not to be used to specify a Satellite server. For that, read"
            " the product documentation at https://access.redhat.com/.",
        )

    def _process_cli_options(self):
        """Process command line options used with the tool."""
        _log_command_used()

        # algorithm function to properly organize all CLI args
        argv = _add_default_command(sys.argv[1:])
        parsed_opts = self._parser.parse_args(argv)

        file_config = FileConfig(parsed_opts.config_file) if parsed_opts.config_file else FileConfig()
        cli_config = CliConfig(parsed_opts)
        initialize_toolopts(
            config_sources=(
                file_config,
                cli_config,
            )
        )

        # Processing the configuration file
        # corner case: password on CLI and activation-key in the config file
        # password from CLI has precedence and activation_key and org must be deleted (unused)
        if parsed_opts.activation_key and parsed_opts.password:
            parsed_opts.activation_key = None
            parsed_opts.org = None

        if parsed_opts.no_rpm_va:
            if parsed_opts.activity == "analyze":
                loggerinst.warning(
                    "We will proceed with ignoring the --no-rpm-va option as running rpm -Va"
                    " in the analysis mode is essential for a complete rollback to the original"
                    " system state at the end of the analysis."
                )
            else:
                message = (
                    "We need to run the 'rpm -Va' command to be able to perform a complete rollback of changes"
                    " done to the system during the pre-conversion analysis. If you accept the risk of an"
                    " incomplete rollback, set the CONVERT2RHEL_INCOMPLETE_ROLLBACK=1 environment"
                    " variable. Otherwise, remove the --no-rpm-va option."
                )
                loggerinst.critical(message)

        # Check if we have duplicate repositories specified
        if parsed_opts.enablerepo or parsed_opts.disablerepo:
            duplicate_repos = set(tool_opts.disablerepo) & set(tool_opts.enablerepo)
            if duplicate_repos:
                message = "Duplicate repositories were found across disablerepo and enablerepo options:"
                for repo in duplicate_repos:
                    message += "\n%s" % repo
                message += "\nThis ambiguity may have unintended consequences."
                loggerinst.warning(message)

        if parsed_opts.no_rhsm:
            tool_opts.no_rhsm = True
            if not tool_opts.enablerepo:
                loggerinst.critical("The --enablerepo option is required when --no-rhsm is used.")

        # Security notice
        if parsed_opts.password or parsed_opts.activationkey:
            loggerinst.warning(
                "Passing the RHSM password or activation key through the --activationkey or --password options is"
                " insecure as it leaks the values through the list of running processes. We recommend using the safer"
                " --config-file option instead."
            )

        # Checks of multiple authentication sources
        if parsed_opts.password and parsed_opts.activation_key:
            loggerinst.warning(
                "Either a password or an activation key can be used for system registration."
                " We're going to use the activation key."
            )

        if (parsed_opts.org and not parsed_opts.activation_key) or (not parsed_opts.org and parsed_opts.activation_key):
            loggerinst.critical(
                "Either the --org or the --activationkey option is missing. You can't use one without the other."
            )

        # Config files matches
        # if config_opts.username and parsed_opts.username:
        #     loggerinst.warning(
        #         "You have passed the RHSM username through both the command line and the"
        #         " configuration file. We're going to use the command line values."
        #     )

        # if config_opts.org and parsed_opts.org:
        #     loggerinst.warning(
        #         "You have passed the RHSM org through both the command line and the"
        #         " configuration file. We're going to use the command line values."
        #     )

        # if (config_opts.activation_key or config_opts.password) and (parsed_opts.activationkey or parsed_opts.password):
        #     loggerinst.warning(
        #         "You have passed either the RHSM password or activation key through both the command line and the"
        #         " configuration file. We're going to use the command line values."
        #     )

        # if (parsed_opts.password or config_opts.password) and not (parsed_opts.username or config_opts.username):
        #     loggerinst.warning(
        #         "You have passed the RHSM password without an associated username. Please provide a username together"
        #         " with the password."
        #     )

        # if (parsed_opts.username or config_opts.username) and not (parsed_opts.password or config_opts.password):
        #     loggerinst.warning(
        #         "You have passed the RHSM username without an associated password. Please provide a password together"
        #         " with the username."
        #     )


def _log_command_used():
    """We want to log the command used for convert2rhel to make it easier to know what command was used
    when debugging the log files. Since we can't differentiate between the handlers we log to both stdout
    and the logfile
    """
    command = " ".join(utils.hide_secrets(sys.argv))
    loggerinst.info("convert2rhel command used:\n{0}".format(command))


def _add_default_command(argv):
    """Add the default command when none is given"""
    subcommand = _subcommand_used(argv)
    args = argv
    if not subcommand:
        args.insert(0, "convert")

    return args


def _subcommand_used(args):
    """Return what subcommand has been used by the user. Return None if no subcommand has been used."""
    for index, argument in enumerate(args):
        if argument in ("convert", "analyze"):
            return argument

        if not argument in PARENT_ARGS and args[index - 1] in ARGS_WITH_VALUES:
            return None
