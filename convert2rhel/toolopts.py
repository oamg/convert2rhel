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

import argparse
import copy
import logging
import os
import re
import sys

from six.moves import configparser, urllib

from convert2rhel import __version__, utils


loggerinst = logging.getLogger(__name__)

# Paths for configuration files
CONFIG_PATHS = ["~/.convert2rhel.ini", "/etc/convert2rhel.ini"]

#: Map name of the convert2rhel mode to run in from the command line to the
#: activity name that we use in the code and breadcrumbs.  CLI commands should
#: be verbs but an activity is a noun.
_COMMAND_TO_ACTIVITY = {
    "convert": "conversion",
    "analyze": "analysis",
    "analyse": "analysis",
}

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

# For a list of modified rpm files before the conversion starts
PRE_RPM_VA_LOG_FILENAME = "rpm_va.log"

# For a list of modified rpm files after the conversion finishes for comparison purposes
POST_RPM_VA_LOG_FILENAME = "rpm_va_after_conversion.log"

CONFIG_FILE_MAPPING_OPTIONS = {
    "subscription_manager": ["username", "password", "org", "activation_key"],
    "settings": [
        "incomplete_rollback",
        "tainted_kernel_module_check_skip",
        "outdated_package_check_skip",
        "allow_older_version",
        "allow_unavailable_kmods",
        "configure_host_metering",
        "skip_kernel_currency_check",
    ],
}


class ToolOpts:
    def __init__(self):
        self.debug = False
        self.username = None
        self.config_file = None
        self.password = None
        self.no_rhsm = False
        self.enablerepo = []
        self.disablerepo = []
        self.pool = None
        self.rhsm_hostname = None
        self.rhsm_port = None
        self.rhsm_prefix = None
        self.autoaccept = None
        self.auto_attach = None
        self.restart = None
        self.activation_key = None
        self.org = None
        self.arch = None
        self.no_rpm_va = False
        self.eus = False
        self.els = False
        self.activity = None

        # Settings
        self.incomplete_rollback = None
        self.tainted_kernel_module_check_skip = None
        self.outdated_package_check_skip = None
        self.allow_older_version = None
        self.allow_unavailable_kmods = None
        self.configure_host_metering = None
        self.skip_kernel_currency_check = None

    def set_opts(self, supported_opts):
        """Set ToolOpts data using dict with values from config file.

        :param supported_opts: Supported options in config file
        """
        for key, value in supported_opts.items():
            if value and hasattr(self, key):
                setattr(self, key, value)


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

        if parsed_opts.debug:
            tool_opts.debug = True

        # Once we use a subcommand to set the activity that convert2rhel will perform
        tool_opts.activity = _COMMAND_TO_ACTIVITY[parsed_opts.command]

        # Processing the configuration file
        conf_file_opts = options_from_config_files(parsed_opts.config_file)
        tool_opts.set_opts(conf_file_opts)
        config_opts = copy.copy(tool_opts)
        tool_opts.config_file = parsed_opts.config_file
        # corner case: password on CLI and activation-key in the config file
        # password from CLI has precedence and activation_key and org must be deleted (unused)
        if config_opts.activation_key and parsed_opts.password:
            tool_opts.activation_key = None
            tool_opts.org = None

        if parsed_opts.no_rpm_va:
            if tool_opts.activity == "analysis":
                loggerinst.warning(
                    "We will proceed with ignoring the --no-rpm-va option as running rpm -Va"
                    " in the analysis mode is essential for a complete rollback to the original"
                    " system state at the end of the analysis."
                )
            elif os.getenv("CONVERT2RHEL_INCOMPLETE_ROLLBACK", None):
                tool_opts.no_rpm_va = True
            else:
                message = (
                    "We need to run the 'rpm -Va' command to be able to perform a complete rollback of changes"
                    " done to the system during the pre-conversion analysis. If you accept the risk of an"
                    " incomplete rollback, set the CONVERT2RHEL_INCOMPLETE_ROLLBACK=1 environment"
                    " variable. Otherwise, remove the --no-rpm-va option."
                )
                loggerinst.critical(message)

        if parsed_opts.username:
            tool_opts.username = parsed_opts.username

        if parsed_opts.password:
            tool_opts.password = parsed_opts.password

        if parsed_opts.enablerepo:
            tool_opts.enablerepo = parsed_opts.enablerepo
        if parsed_opts.disablerepo:
            tool_opts.disablerepo = parsed_opts.disablerepo

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

        if parsed_opts.eus:
            tool_opts.eus = True

        if parsed_opts.els:
            tool_opts.els = True

        if not tool_opts.disablerepo:
            # Default to disable every repo except:
            # - the ones passed through --enablerepo
            # - the ones enabled through subscription-manager based on convert2rhel config files
            tool_opts.disablerepo = ["*"]

        if parsed_opts.pool:
            tool_opts.pool = parsed_opts.pool

        if parsed_opts.activationkey:
            tool_opts.activation_key = parsed_opts.activationkey

        if parsed_opts.org:
            tool_opts.org = parsed_opts.org

        if parsed_opts.serverurl:
            if tool_opts.no_rhsm:
                loggerinst.warning("Ignoring the --serverurl option. It has no effect when --no-rhsm is used.")
            # WARNING: We cannot use the following helper until after no_rhsm,
            # username, password, activation_key, and organization have been set.
            elif not _should_subscribe(tool_opts):
                loggerinst.warning(
                    "Ignoring the --serverurl option. It has no effect when no credentials to subscribe the system were given."
                )
            else:
                # Parse the serverurl and save the components.
                try:
                    url_parts = _parse_subscription_manager_serverurl(parsed_opts.serverurl)
                    url_parts = _validate_serverurl_parsing(url_parts)
                except ValueError as e:
                    # If we fail to parse, fail the conversion. The reason for
                    # this harsh treatment is that we will be submitting
                    # credentials to the server parsed from the serverurl. If
                    # the user is specifying an internal subscription-manager
                    # server but typo the url, we would fallback to the
                    # public red hat subscription-manager server. That would
                    # mean the user thinks the credentials are being passed
                    # to their internal subscription-manager server but it
                    # would really be passed externally.  That's not a good
                    # security practice.
                    loggerinst.critical(
                        "Failed to parse a valid subscription-manager server from the --serverurl option.\n"
                        "Please check for typos and run convert2rhel again with a corrected --serverurl.\n"
                        "Supplied serverurl: %s\nError: %s" % (parsed_opts.serverurl, e)
                    )

                tool_opts.rhsm_hostname = url_parts.hostname

                if url_parts.port:
                    # urllib.parse.urlsplit() converts this into an int but we
                    # always use it as a str
                    tool_opts.rhsm_port = str(url_parts.port)

                if url_parts.path:
                    tool_opts.rhsm_prefix = url_parts.path

        tool_opts.autoaccept = parsed_opts.y
        tool_opts.auto_attach = parsed_opts.auto_attach

        # conversion only options
        if tool_opts.activity == "conversion":
            tool_opts.restart = parsed_opts.restart

        # Security notice
        if tool_opts.password or tool_opts.activation_key:
            loggerinst.warning(
                "Passing the RHSM password or activation key through the --activationkey or --password options is"
                " insecure as it leaks the values through the list of running processes. We recommend using the safer"
                " --config-file option instead."
            )

        # Checks of multiple authentication sources
        if tool_opts.password and tool_opts.activation_key:
            loggerinst.warning(
                "Either a password or an activation key can be used for system registration."
                " We're going to use the activation key."
            )

        # Config files matches
        if config_opts.username and parsed_opts.username:
            loggerinst.warning(
                "You have passed the RHSM username through both the command line and the"
                " configuration file. We're going to use the command line values."
            )

        if config_opts.org and parsed_opts.org:
            loggerinst.warning(
                "You have passed the RHSM org through both the command line and the"
                " configuration file. We're going to use the command line values."
            )

        if (config_opts.activation_key or config_opts.password) and (parsed_opts.activationkey or parsed_opts.password):
            loggerinst.warning(
                "You have passed either the RHSM password or activation key through both the command line and the"
                " configuration file. We're going to use the command line values."
            )

        if (tool_opts.org and not tool_opts.activation_key) or (not tool_opts.org and tool_opts.activation_key):
            loggerinst.critical(
                "Either the --org or the --activationkey option is missing. You can't use one without the other."
            )

        if (parsed_opts.password or config_opts.password) and not (parsed_opts.username or config_opts.username):
            loggerinst.warning(
                "You have passed the RHSM password without an associated username. Please provide a username together"
                " with the password."
            )

        if (parsed_opts.username or config_opts.username) and not (parsed_opts.password or config_opts.password):
            loggerinst.warning(
                "You have passed the RHSM username without an associated password. Please provide a password together"
                " with the username."
            )


def options_from_config_files(cfg_path):
    """Parse the convert2rhel.ini configuration file.

    This function will try to parse the convert2rhel.ini configuration file and
    return a dictionary containing the values found in the file.

    .. note::
        This function will parse the configuration file in the following way:

        1) If the path provided by the user in cfg_path is set (Highest
           priority), then we use only that.

        Otherwise, if cfg_path is `None`, we proceed to check the following
        paths:

        2) ~/.convert2rhel.ini (The 2nd highest priority).
        3) /etc/convert2rhel.ini (The lowest priority).

        In any case, they are parsed in reversed order, meaning that we will
        start with the lowest priority and go until the highest.

    :param cfg_path: Path of a custom configuration file
    :type cfg_path: str

    :return: Dict with the supported options alongside their values.
    :rtype: dict[str, str]
    """
    # Paths for the configuration files. In case we have cfg_path defined
    # (meaning that the user entered something through the `-c` option), we
    # will use only that, as it has a higher priority over the rest
    config_paths = [cfg_path] if cfg_path else CONFIG_PATHS
    paths = [os.path.expanduser(path) for path in config_paths if os.path.exists(os.path.expanduser(path))]

    if cfg_path and not paths:
        raise FileNotFoundError("No such file or directory: %s" % ", ".join(paths))

    found_opts = _parse_options_from_config(paths)
    return found_opts


def _parse_options_from_config(paths):
    """Parse the options from the given config files.

    .. note::
        If no configuration file is provided through the command line option
        (`-c`), we will use the default paths and follow their priority.

    :param paths: List of paths to iterate through and gather the options from
        them.
    :type paths: list[str]
    """
    config_file = configparser.ConfigParser()
    found_opts = {}

    for path in reversed(paths):
        loggerinst.debug("Checking configuration file at %s" % path)
        # Check for correct permissions on file
        if not oct(os.stat(path).st_mode)[-4:].endswith("00"):
            loggerinst.critical("The %s file must only be accessible by the owner (0600)" % path)

        config_file.read(path)

        # Mapping of all supported options we can have in the config file
        for supported_header, supported_opts in CONFIG_FILE_MAPPING_OPTIONS.items():
            loggerinst.debug("Checking for header '%s'" % supported_header)
            if supported_header not in config_file.sections():
                loggerinst.warning("Couldn't find header '%s' in the configuration file %s." % (supported_header, path))
                continue

            options = _get_options_value(config_file, supported_header, supported_opts)
            found_opts.update(options)

    return found_opts


def _get_options_value(config_file, header, supported_opts):
    """Helper function to iterate through the options in a config file.

    :param config_file: An instance of `py:ConfigParser` after reading the file
        to iterate through the options.
    :type config_file: configparser.ConfigParser
    :param header: The header name to get options from.
    :type header: str
    :param supported_opts: List of supported options that can be parsed from
        the config file.
    :type supported_opts: list[str]
    """
    options = {}
    conf_options = config_file.options(header)

    if len(conf_options) == 0:
        loggerinst.debug("No options found for %s. It seems to be empty or commented." % header)
        return options

    for option in conf_options:
        if option.lower() not in supported_opts:
            loggerinst.warning("Unsupported option '%s' in '%s'" % (option, header))
            continue

        options[option] = config_file.get(header, option).strip('"')
        loggerinst.debug("Found %s in %s" % (option, header))

    return options


def _log_command_used():
    """We want to log the command used for convert2rhel to make it easier to know what command was used
    when debugging the log files. Since we can't differentiate between the handlers we log to both stdout
    and the logfile
    """
    command = " ".join(utils.hide_secrets(sys.argv))
    loggerinst.info("convert2rhel command used:\n{0}".format(command))


def _parse_subscription_manager_serverurl(serverurl):
    """Parse a url string in a manner mostly compatible with subscription-manager --serverurl."""
    # This is an adaptation of what subscription-manager's cli enforces:
    # https://github.com/candlepin/subscription-manager/blob/main/src/rhsm/utils.py#L112

    # Don't modify http://<something> and https://<something> as they are fine
    if not re.match("https?://[^/]+", serverurl):
        # Anthing that looks like a malformed scheme is immediately discarded
        if re.match("^[^:]+:/.+", serverurl):
            raise ValueError("Unable to parse --serverurl. Make sure it starts with http://HOST or https://HOST")

        # If there isn't a scheme, add one now
        serverurl = "https://%s" % serverurl

    url_parts = urllib.parse.urlsplit(serverurl, allow_fragments=False)

    return url_parts


def _validate_serverurl_parsing(url_parts):
    """
    Perform some tests that we parsed the subscription-manager serverurl successfully.

    :arg url_parts: The parsed serverurl as returned by urllib.parse.urlsplit()
    :raises ValueError: If any of the checks fail.
    :returns: url_parts If the check was successful.
    """
    if url_parts.scheme not in ("https", "http"):
        raise ValueError(
            "Subscription manager must be accessed over http or https.  %s is not valid" % url_parts.scheme
        )

    if not url_parts.hostname:
        raise ValueError("A hostname must be specified in a subscription-manager serverurl")

    return url_parts


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


def _should_subscribe(tool_opts):
    """
    Whether we should subscribe the system with subscription-manager.

    If there are no ways to authenticate to subscription-manager, then we will attempt to convert
    without subscribing the system.  The assumption is that the user has already subscribed the
    system or that this machine does not need to subscribe to rhsm in order to get the RHEL rpm
    packages.
    """
    # No means to authenticate with rhsm.
    if not (tool_opts.username and tool_opts.password) and not (tool_opts.activation_key and tool_opts.org):
        return False

    # --no-rhsm means that there is no need to use any part of rhsm to
    # convert this host.  (Usually used when you configure
    # your RHEL repos another way, like a local mirror and telling
    # convert2rhel about it using --enablerepo)
    if tool_opts.no_rhsm:
        return False

    return True


# Code to be executed upon module import
tool_opts = ToolOpts()  # pylint: disable=C0103
