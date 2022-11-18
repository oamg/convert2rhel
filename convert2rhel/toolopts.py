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

import copy
import logging
import optparse
import os
import re
import sys

from six.moves import configparser, urllib

from convert2rhel import __version__, utils


loggerinst = logging.getLogger(__name__)

# Paths for configuration files
CONFIG_PATHS = ["~/.convert2rhel.ini", "/etc/convert2rhel.ini"]


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
        self._register_options()
        self._process_cli_options()

    @staticmethod
    def _get_argparser():
        usage = (
            "\n"
            "  convert2rhel [-h]\n"
            "  convert2rhel [--version]\n"
            "  convert2rhel [-u username] [-p password | -c conf_file_path] [--pool pool_id | -a] [--disablerepo repoid]"
            " [--enablerepo repoid] [--serverurl url] [--keep-rhsm] [--no-rpm-va] [--debug] [--restart]"
            " [-y]\n"
            "  convert2rhel [--no-rhsm] [--disablerepo repoid]"
            " [--enablerepo repoid] [--no-rpm-va] [--debug] [--restart] [-y]\n"
            "  convert2rhel [-k activation_key | -c conf_file_path] [-o organization] [--pool pool_id | -a] [--disablerepo repoid] [--enablerepo"
            " repoid] [--serverurl url] [--keep-rhsm] [--no-rpm-va] [--debug] [--restart] [-y]"
            "\n\n"
            "WARNING: The tool needs to be run under the root user"
        )
        return optparse.OptionParser(
            conflict_handler="resolve",
            usage=usage,
            add_help_option=False,
            version=__version__,
        )

    def _register_options(self):
        """Prescribe what command line options the tool accepts."""
        self._parser.add_option(
            "-h",
            "--help",
            action="help",
            help="Show help message and exit.",
        )
        self._parser.add_option(
            "--version",
            action="version",
            help="Show convert2rhel version and exit.",
        )
        self._parser.add_option(
            "--debug",
            action="store_true",
            help="Print traceback in case of an abnormal exit and messages that could help find an issue.",
        )
        # Importing here instead of on top of the file to avoid cyclic dependency
        from convert2rhel.systeminfo import POST_RPM_VA_LOG_FILENAME, PRE_RPM_VA_LOG_FILENAME

        self._parser.add_option(
            "--no-rpm-va",
            action="store_true",
            help="Skip gathering changed rpm files using"
            " 'rpm -Va'. By default it's performed before and after the conversion with the output"
            " stored in log files %s and %s. At the end of the conversion, these logs are compared"
            " to show you what rpm files have been affected by the conversion."
            % (PRE_RPM_VA_LOG_FILENAME, POST_RPM_VA_LOG_FILENAME),
        )
        self._parser.add_option(
            "--enablerepo",
            metavar="repoidglob",
            action="append",
            help="Enable specific"
            " repositories by ID or glob. For more repositories to enable, use this option"
            " multiple times. If you don't use the --no-rhsm option, you can use this option"
            " to override the default RHEL repoids that convert2rhel enables through"
            " subscription-manager.",
        )
        self._parser.add_option(
            "--disablerepo",
            metavar="repoidglob",
            action="append",
            help="Disable specific"
            " repositories by ID or glob. For more repositories to disable, use this option"
            " multiple times. This option defaults to all repositories ('*').",
        )
        group = optparse.OptionGroup(
            self._parser,
            "Subscription Manager Options",
            "The following options are specific to using subscription-manager.",
        )
        group.add_option(
            "-u",
            "--username",
            help="Username for the"
            " subscription-manager. If neither --username nor"
            " --activation-key option is used, the user"
            " is asked to enter the username.",
        )
        group.add_option(
            "-p",
            "--password",
            help="Password for the"
            " subscription-manager. If --password, --config-file or --activationkey are not"
            " used, the user is asked to enter the password."
            " We recommend using the --config-file option instead to prevent leaking the password"
            " through a list of running processes.",
        )
        group.add_option(
            "-f",
            "--password-from-file",
            help="File containing"
            " password for the subscription-manager in the plain"
            " text form. It's an alternative to the --password"
            " option. Deprecated, use --config-file instead.",
        )
        group.add_option(
            "-k",
            "--activationkey",
            help="Activation key used"
            " for the system registration by the"
            " subscription-manager. It requires to have the --org"
            " option specified."
            " We recommend using the --config-file option instead to prevent leaking the activation key"
            " through a list of running processes.",
        )
        group.add_option(
            "-o",
            "--org",
            help="Organization with which the"
            " system will be registered by the"
            " subscription-manager. A list of available"
            " organizations is possible to obtain by running"
            " 'subscription-manager orgs'. From the listed pairs"
            " Name:Key, use the Key here.",
        )
        group.add_option(
            "-c",
            "--config-file",
            help="A configuration file to safely provide either a user password or an activation key for registering"
            " the system through subscription-manager. Alternatively, passing these values through the"
            " --activationkey or --password option would leak them through a list of running processes."
            " Example of this file in /etc/convert2rhel.ini",
        )
        group.add_option(
            "-a",
            "--auto-attach",
            help="Automatically attach compatible subscriptions to the system.",
            action="store_true",
        )
        group.add_option(
            "--pool",
            help="Subscription pool ID. If not used,"
            " the user is asked to choose from the available"
            " subscriptions. A list of the available"
            " subscriptions is possible to obtain by running"
            " 'subscription-manager list --available'.",
        )
        group.add_option(
            "-v",
            "--variant",
            help="This option is not supported anymore and has no effect. When"
            " converting a system to RHEL 6 or 7 using subscription-manager,"
            " the system is now always converted to the Server variant. In case"
            " of using custom repositories, the system is converted to the variant"
            " provided by these repositories.",
        )
        group.add_option(
            "--serverurl",
            help="Hostname of the subscription service with which to register the system through subscription-manager."
            " The default is the Customer Portal Subscription Management service. It is not to be used to specify a"
            " Satellite server. For that, read the product documentation at https://access.redhat.com/.",
        )
        group.add_option(
            "--keep-rhsm",
            action="store_true",
            help="Keep the already installed Red Hat Subscription Management-related packages. By default,"
            " during the conversion, these packages are removed, downloaded from verified sources and re-installed."
            " This option is suitable for environments with no connection to the Internet, or for systems managed by"
            " Red Hat Satellite. Warning: The system is being re-registered during the conversion and when the"
            " re-registration fails, there's no automated rollback to the original registration.",
        )
        self._parser.add_option_group(group)

        group = optparse.OptionGroup(
            self._parser,
            "Alternative Installation Options",
            "The following options are required if you do not intend on using subscription-manager",
        )
        group.add_option(
            "--disable-submgr",
            action="store_true",
            help="Replaced by --no-rhsm. Both options have the same effect.",
        )
        group.add_option(
            "--no-rhsm",
            action="store_true",
            help="Do not use the subscription-manager, use custom repositories instead. See --enablerepo/--disablerepo"
            " options. Without this option, the subscription-manager is used to access RHEL repositories by default."
            " Using this option requires to have the --enablerepo specified.",
        )
        self._parser.add_option_group(group)

        group = optparse.OptionGroup(
            self._parser,
            "Automation Options",
            "The following options are used to automate the installation",
        )
        group.add_option(
            "-r",
            "--restart",
            help="Restart the system when it is successfully converted to RHEL to boot the new RHEL kernel.",
            action="store_true",
        )
        group.add_option(
            "-y",
            help="Answer yes to all yes/no questions the tool asks.",
            action="store_true",
        )
        self._parser.add_option_group(group)

    def _process_cli_options(self):
        """Process command line options used with the tool."""
        _log_command_used()

        warn_on_unsupported_options()

        parsed_opts, _ = self._parser.parse_args()

        global tool_opts  # pylint: disable=C0103

        if parsed_opts.debug:
            tool_opts.debug = True

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
    :rtype: dict[str | None, str | None]
    """
    headers = ["subscription_manager"]  # supported sections in config file
    config_file = configparser.ConfigParser()
    paths = [os.path.expanduser(path) for path in CONFIG_PATHS]
    # Create dict with all supported options, all of them set to None
    # needed for avoiding problems with files priority
    # The name of supported option MUST correspond with the name in ToolOpts()
    # Otherwise it won't be used
    supported_opts = {"password": None, "activation_key": None}

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


# Code to be executed upon module import
tool_opts = ToolOpts()  # pylint: disable=C0103
