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
    "-f",
    "--password-from-file",
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


class ToolOpts(object):
    def __init__(self):
        self.debug = False
        self.username = None
        self.password_file = None
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
        self.keep_rhsm = False
        self.activity = None

        # set True when credentials (username & password) are given through CLI
        self.credentials_thru_cli = False

    def set_opts(self, supported_opts):
        """Set ToolOpts data using dict with values from config file.

        :param supported_opts: Supported options in config file
        """
        for key, value in supported_opts.items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)


class CLI(object):
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

    @property
    def usage(self):
        usage = (
            "\n"
            "  convert2rhel\n"
            "  convert2rhel [-h]\n"
            "  convert2rhel [--version]\n"
            "  convert2rhel [-u username] [-p password | -c conf_file_path] [--pool pool_id | -a] [--disablerepo repoid]"
            " [--enablerepo repoid] [--serverurl url] [--keep-rhsm] [--no-rpm-va] [--debug] [--restart]"
            " [-y]\n"
            "  convert2rhel [--no-rhsm] [--disablerepo repoid]"
            " [--enablerepo repoid] [--no-rpm-va] [--debug] [--restart] [-y]\n"
            "  convert2rhel [-k activation_key | -c conf_file_path] [-o organization] [--pool pool_id | -a] [--disablerepo repoid] [--enablerepo"
            " repoid] [--serverurl url] [--keep-rhsm] [--no-rpm-va] [--debug] [--restart] [-y]\n"
            r" convert2rhel {analyze}"
            "\n\n"
            "*WARNING* The tool needs to be run under the root user\n"
        )
        return usage

    def _get_argparser(self):
        return argparse.ArgumentParser(conflict_handler="resolve", usage=self.usage)

    def _register_commands(self):
        """Configures parsers specific to the analyze and convert subcommands"""
        subparsers = self._parser.add_subparsers(title="Subcommands", dest="command")
        self._analyze_parser = subparsers.add_parser(
            "analyze",
            help="Run all Convert2RHEL initial checks up until the "
            " Point of no Return (PONR) and generate a report with the findings."
            " A rollback is initiated after the checks to put the system back"
            " in the original state.",
            parents=[self._shared_options_parser],
            usage=self.usage,
        )
        self._convert_parser = subparsers.add_parser(
            "convert",
            help="Convert the system.",
            parents=[self._shared_options_parser],
            usage=self.usage,
        )

    def _register_parent_options(self, parser):
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
            % (PRE_RPM_VA_LOG_FILENAME, POST_RPM_VA_LOG_FILENAME),
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

        self._add_subscription_manager_options()
        self._add_alternative_installation_options()
        self._register_commands()
        self._add_automation_options(self._convert_parser, restart=True)
        self._add_automation_options(self._analyze_parser, restart=False)

    def _add_automation_options(self, parser, restart):
        """Prescribe what automation command line options the tool accepts."""
        group = parser.add_argument_group(
            title="Automation Options",
            description="The following options are used to automate the installation",
        )
        if restart:
            group.add_argument(
                "-r",
                "--restart",
                help="Restart the system when it is successfully converted to RHEL to boot the new RHEL kernel.",
                action="store_true",
            )
        group.add_argument(
            "-y",
            help="Answer yes to all yes/no questions the tool asks.",
            action="store_true",
        )

    def _add_alternative_installation_options(self):
        """Prescribe what alternative command line options the tool accepts."""
        group = self._shared_options_parser.add_argument_group(
            title="Alternative Installation Options",
            description="The following options are required if you do not intend on using subscription-manager",
        )
        group.add_argument(
            "--disable-submgr",
            action="store_true",
            help="Replaced by --no-rhsm. Both options have the same effect.",
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
            "-f",
            "--password-from-file",
            help="File containing"
            " password for the subscription-manager in the plain"
            " text form. It's an alternative to the --password"
            " option. Deprecated, use --config-file instead.",
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
            "-v",
            "--variant",
            help="This option is not supported anymore and has no effect. When"
            " converting a system to RHEL 7 using subscription-manager,"
            " the system is now always converted to the Server variant. In case"
            " of using custom repositories, the system is converted to the variant"
            " provided by these repositories.",
        )
        group.add_argument(
            "--serverurl",
            help="Hostname of the subscription service with which to register the system through subscription-manager."
            " The default is the Customer Portal Subscription Management service. It is not to be used to specify a"
            " Satellite server. For that, read the product documentation at https://access.redhat.com/.",
        )
        group.add_argument(
            "--keep-rhsm",
            action="store_true",
            help="Keep the already installed Red Hat Subscription Management-related packages. By default,"
            " during the conversion, these packages are removed, downloaded from verified sources and re-installed."
            " This option is suitable for environments with no connection to the Internet, or for systems managed by"
            " Red Hat Satellite. Warning: The system is being re-registered during the conversion and when the"
            " re-registration fails, there's no automated rollback to the original registration.",
        )

    def _process_cli_options(self):
        """Process command line options used with the tool."""
        _log_command_used()

        warn_on_unsupported_options()

        # algorithm function to properly organize all CLI args
        argv = _add_default_command(sys.argv[1:])
        parsed_opts = self._parser.parse_args(argv)

        if parsed_opts.debug:
            tool_opts.debug = True

        if hasattr(parsed_opts, "command"):
            # Once we use a subcommand to set the activity that convert2rhel will perform
            tool_opts.activity = _COMMAND_TO_ACTIVITY[parsed_opts.command]
        else:
            # At first, in tech preview, we use an environment variable to set the activity.
            experimental_analysis = bool(os.getenv("CONVERT2RHEL_EXPERIMENTAL_ANALYSIS", None))
            if experimental_analysis:
                tool_opts.activity = "analysis"
            else:
                tool_opts.activity = "conversion"

        # Processing the configuration file
        conf_file_opts = options_from_config_files(parsed_opts.config_file)
        ToolOpts.set_opts(tool_opts, conf_file_opts)  # pylint: disable=E0601
        config_opts = copy.copy(tool_opts)
        tool_opts.config_file = parsed_opts.config_file
        # corner case: password on CLI or in password file and activation-key in the config file
        # password from CLI has precedence and activation-key must be deleted (unused)
        if config_opts.activation_key and (parsed_opts.password or parsed_opts.password_from_file):
            tool_opts.activation_key = None

        if parsed_opts.no_rpm_va:
            tool_opts.no_rpm_va = True

        if parsed_opts.username:
            tool_opts.username = parsed_opts.username

        if parsed_opts.password:
            tool_opts.password = parsed_opts.password

        if parsed_opts.password_from_file:
            loggerinst.warning("Deprecated. Use -c | --config-file instead.")
            tool_opts.password_file = parsed_opts.password_from_file
            tool_opts.password = utils.get_file_content(parsed_opts.password_from_file)

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

        if parsed_opts.no_rhsm or parsed_opts.disable_submgr:
            tool_opts.no_rhsm = True
            if not tool_opts.enablerepo:
                loggerinst.critical("The --enablerepo option is required when --disable-submgr or --no-rhsm is used.")
        if not tool_opts.disablerepo:
            # Default to disable every repo except:
            # - the ones passed through --enablerepo
            # - the ones enabled through subscription-manager based on convert2rhel config files
            tool_opts.disablerepo = ["*"]

        if parsed_opts.pool:
            tool_opts.pool = parsed_opts.pool

        if parsed_opts.serverurl:
            if tool_opts.no_rhsm:
                loggerinst.warning(
                    "Ignoring the --serverurl option. It has no effect when --disable-submgr or --no-rhsm is used."
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

        if parsed_opts.keep_rhsm:
            if tool_opts.no_rhsm:
                loggerinst.warning(
                    "Ignoring the --keep-rhsm option. It has no effect when --disable-submgr or --no-rhsm is used."
                )
            else:
                tool_opts.keep_rhsm = parsed_opts.keep_rhsm

        tool_opts.autoaccept = parsed_opts.y
        tool_opts.auto_attach = parsed_opts.auto_attach

        # conversion only options
        if tool_opts.activity == "conversion":
            tool_opts.restart = parsed_opts.restart

        if parsed_opts.activationkey:
            tool_opts.activation_key = parsed_opts.activationkey

        if parsed_opts.org:
            tool_opts.org = parsed_opts.org

        # Checks of multiple authentication sources
        if tool_opts.password and tool_opts.activation_key:
            loggerinst.warning(
                "Passing the RHSM password or activation key through the --activationkey or --password options is"
                " insecure as it leaks the values through the list of running processes. We recommend using the safer"
                " --config-file option instead."
            )
            loggerinst.warning(
                "Either a password or an activation key can be used for system registration."
                " We're going to use the activation key."
            )

        if parsed_opts.password and parsed_opts.password_from_file:
            loggerinst.warning(
                "You have passed the RHSM password through both the --password-from-file and the --password option."
                " We're going to use the password from file."
            )

        # Config files matches
        if config_opts.username or config_opts.org:
            loggerinst.warning(
                "You have passed the RHSM username through both the command line and the"
                " configuration file. We're going to use the command line values."
            )

        if parsed_opts.username or parsed_opts.org:
            loggerinst.warning(
                "You have passed the RHSM org through both the command line and the"
                " configuration file. We're going to use the command line values."
            )

        if (config_opts.activation_key or config_opts.password) and (parsed_opts.activationkey or parsed_opts.password):
            loggerinst.warning(
                "You have passed either the RHSM password or activation key through both the command line and the"
                " configuration file. We're going to use the command line values."
            )

        if (config_opts.activation_key or config_opts.password) and parsed_opts.password_from_file:
            loggerinst.warning(
                "You have passed the RHSM credentials both through a config file and through a password file."
                " We're going to use the password file."
            )

        if (tool_opts.org and not tool_opts.activation_key) or (not tool_opts.org and tool_opts.activation_key):
            loggerinst.critical(
                "Either the --organization or the --activationkey option is missing. You can't use one without the other."
            )

        if tool_opts.username and tool_opts.password:
            tool_opts.credentials_thru_cli = True


def warn_on_unsupported_options():
    if any(x in sys.argv[1:] for x in ["--variant", "-v"]):
        loggerinst.warning(
            "The -v|--variant option is not supported anymore and has no effect.\n"
            "See help (convert2rhel -h) for more information."
        )
        utils.ask_to_continue()


def _log_command_used():
    """We want to log the command used for convert2rhel to make it easier to know what command was used
    when debugging the log files. Since we can't differentiate between the handlers we log to both stdout
    and the logfile
    """
    command = " ".join(utils.hide_secrets(sys.argv))
    loggerinst.info("convert2rhel command used:\n{0}".format(command))


def options_from_config_files(cfg_path=None):
    """Parse the convert2rhel.ini configuration file.

    This function will try to parse the convert2rhel.ini configuration file and
    return a dictionary containing the values found in the file.

    .. note::
       This function will parse the configuration file following a specific
       order, which is:
       1) Path provided by the user in cfg_path (Highest priority).
       2) ~/.convert2rhel.ini (The 2nd highest priority).
       3) /etc/convert2rhel.ini (The lowest priority).

    :param cfg_path: Path of a custom configuration file
    :type cfg_path: str

    :return: Dict with the supported options alongside their values.
    :rtype: dict[str, str | None]
    """
    headers = ["subscription_manager"]  # supported sections in config file
    # Create dict with all supported options, all of them set to None
    # needed for avoiding problems with files priority
    # The name of supported option MUST correspond with the name in ToolOpts()
    # Otherwise it won't be used
    supported_opts = {"username": None, "password": None, "activation_key": None, "org": None}

    config_file = configparser.ConfigParser()
    paths = [os.path.expanduser(path) for path in CONFIG_PATHS]

    if cfg_path:
        cfg_path = os.path.expanduser(cfg_path)
        if not os.path.exists(cfg_path):
            raise OSError(2, "No such file or directory: '%s'" % cfg_path)
        paths.insert(0, cfg_path)  # highest priority

    for path in paths:
        if os.path.exists(path):
            if not oct(os.stat(path).st_mode)[-4:].endswith("00"):
                loggerinst.critical("The %s file must only be accessible by the owner (0600)" % path)
            config_file.read(path)

            for header in config_file.sections():
                if header in headers:
                    for option in config_file.options(header):
                        if option.lower() in supported_opts:
                            # Solving priority
                            if supported_opts[option.lower()] is None:
                                supported_opts[option] = config_file.get(header, option)
                                loggerinst.debug("Found %s in %s" % (option, path))
                        else:
                            loggerinst.warning("Unsupported option %s in %s" % (option, path))
                elif header not in headers and header != "DEFAULT":
                    loggerinst.warning("Unsupported header %s in %s." % (header, path))

    return supported_opts


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
    args = argv
    for index, argument in enumerate(args):
        if argument in ("convert", "analyze"):
            return args
        if not argument in PARENT_ARGS and argv[index - 1] in ARGS_WITH_VALUES:
            break

    args.insert(0, "convert")
    return args


# Code to be executed upon module import
tool_opts = ToolOpts()  # pylint: disable=C0103
