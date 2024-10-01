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

import abc
import copy
import logging
import os

import six

from six.moves import configparser


loggerinst = logging.getLogger(__name__)

#: Map name of the convert2rhel mode to run in from the command line to the
#: activity name that we use in the code and breadcrumbs.  CLI commands should
#: be verbs but an activity is a noun.
_COMMAND_TO_ACTIVITY = {
    "convert": "conversion",
    "analyze": "analysis",
    "analyse": "analysis",
}

# Mapping of supported headers and options for each configuration in the
# `convert2rhel.ini` file we support.
CONFIG_FILE_MAPPING_OPTIONS = {
    "subscription_manager": ["username", "password", "org", "activation_key"],
    "host_metering": ["configure_host_metering"],
    "inhibitor_overrides": [
        "incomplete_rollback",
        "tainted_kernel_module_check_skip",
        "allow_older_version",
        "allow_unavailable_kmods",
        "configure_host_metering",
        "skip_kernel_currency_check",
    ],
}

BOOLEAN_OPTIONS_HEADERS = ["inhibitor_overrides"]


@six.add_metaclass(abc.ABCMeta)
class BaseConfig:
    def set_opts(self, supported_opts):
        """Set ToolOpts data using dict with values from Config classes.

        :param opts: Supported options in config file
        """
        for key, value in supported_opts.items():
            if value and hasattr(self, key):
                setattr(self, key, value)


class FileConfig(BaseConfig):
    SOURCE = "configuration file"
    DEFAULT_CONFIG_FILES = ["~/.convert2rhel.ini", "/etc/convert2rhel.ini"]

    def __init__(self, custom_config):
        super(FileConfig, self).__init__()

        # Subscription Manager
        self.username = None  # type: str | None
        self.password = None  # type: str | None
        self.org = None  # type: str | None
        self.activation_key = None  # type: str | None

        # Inhibitor Override
        self.incomplete_rollback = None  # type: str | None
        self.tainted_kernel_module_check_skip = None  # type: str | None
        self.outdated_package_check_skip = None  # type: str | None
        self.allow_older_version = None  # type: str | None
        self.allow_unavailable_kmods = None  # type: str | None
        self.skip_kernel_currency_check = None  # type: str | None

        # Host metering
        self.configure_host_metering = None  # type: str | None

        self._config_files = self.DEFAULT_CONFIG_FILES
        if custom_config:
            self._config_files.insert(0, custom_config)

    def run(self):
        unparsed_opts = self.options_from_config_files()
        self.set_opts(unparsed_opts)

        # Cleanup
        del self._config_files

    def options_from_config_files(self):
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
        paths = [os.path.expanduser(path) for path in self._config_files if os.path.exists(os.path.expanduser(path))]

        if not paths:
            raise FileNotFoundError("No such file or directory: {}".format(", ".join(paths)))

        found_opts = self._parse_options_from_config(paths)
        return found_opts

    def _parse_options_from_config(self, paths):
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
            loggerinst.debug("Checking configuration file at {}".format(path))
            # Check for correct permissions on file
            if not oct(os.stat(path).st_mode)[-4:].endswith("00"):
                loggerinst.critical("The {} file must only be accessible by the owner (0600)".format(path))

            config_file.read(path)

            # Mapping of all supported options we can have in the config file
            for supported_header, supported_opts in CONFIG_FILE_MAPPING_OPTIONS.items():
                loggerinst.debug("Checking for header '{}'".format(supported_header))
                if supported_header not in config_file.sections():
                    loggerinst.warning(
                        "Couldn't find header '{}' in the configuration file {}.".format(supported_header, path)
                    )
                    continue
                options = self._get_options_value(config_file, supported_header, supported_opts)
                found_opts.update(options)

        return found_opts

    def _get_options_value(self, config_file, header, supported_opts):
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
            loggerinst.debug("No options found for {}. It seems to be empty or commented.".format(header))
            return options

        for option in conf_options:
            if option.lower() not in supported_opts:
                loggerinst.warning("Unsupported option '{}' in '{}'".format(option, header))
                continue

            # This is the only header that can contain boolean values for now.
            if header in BOOLEAN_OPTIONS_HEADERS:
                options[option] = config_file.getboolean(header, option)
            else:
                options[option] = config_file.get(header, option)

            loggerinst.debug("Found {} in {}".format(option, header))

        return options


class CliConfig(BaseConfig):
    SOURCE = "command line"

    def __init__(self, opts):
        super(CliConfig, self).__init__()

        self.debug = False  # type: bool
        self.username = None  # type: str | None
        self.password = None  # type: str | None
        self.org = None  # type: str | None
        self.activation_key = None  # type: str | None
        self.config_file = None  # type: str | None
        self.no_rhsm = False  # type: bool
        self.enablerepo = []  # type: list[str]
        self.disablerepo = []  # type: list[str]
        self.pool = None  # type: str | None
        self.autoaccept = False  # type: bool
        self.auto_attach = None  # type: str | None
        self.restart = False  # type: bool
        self.arch = None  # type: str | None
        self.no_rpm_va = False  # type: bool
        self.eus = False  # type: bool
        self.els = False  # type: bool
        self.activity = None  # type: str | None
        self.serverurl = None  # type: str | None

        self._opts = opts  # type: arpgparse.Namepsace

    def run(self):
        opts = vars(self._opts)

        opts = self._normalize_opts(opts)
        self._validate(opts)
        self.set_opts(opts)

        # Cleanup
        del self._opts

    def _normalize_opts(self, opts):
        unparsed_opts = copy.copy(opts)
        unparsed_opts["activity"] = _COMMAND_TO_ACTIVITY[opts.get("command", "convert")]
        unparsed_opts["disablerepo"] = opts.get("disablerepo") if opts["disablerepo"] else ["*"]
        unparsed_opts["enablerepo"] = opts.get("enablerepo") if opts["enablerepo"] else []
        unparsed_opts["autoaccept"] = opts.get("auto_accept") if opts["auto_accept"] else False

        # Conversion only opts.
        if unparsed_opts["activity"] == "conversion":
            unparsed_opts["restart"] = opts.get("restart")

        if unparsed_opts["no_rpm_va"]:
            if unparsed_opts["activity"] == "analysis":
                loggerinst.warning(
                    "We will proceed with ignoring the --no-rpm-va option as running rpm -Va"
                    " in the analysis mode is essential for a complete rollback to the original"
                    " system state at the end of the analysis."
                )
                unparsed_opts["no_rpm_va"] = False

        # This is not needed at the data structure. Command is something that comes from the argparse.Namespace
        # strucutre.
        del unparsed_opts["command"]

        return unparsed_opts

    def _validate(self, opts):
        # Security notice
        if opts["password"] or opts["activation_key"]:
            loggerinst.warning(
                "Passing the RHSM password or activation key through the --activationkey or --password options is"
                " insecure as it leaks the values through the list of running processes. We recommend using the safer"
                " --config-file option instead."
            )

        # Checks of multiple authentication sources
        if opts["password"] and opts["activation_key"]:
            loggerinst.warning(
                "Either a password or an activation key can be used for system registration."
                " We're going to use the activation key."
            )

        if opts["username"] and not opts["password"]:
            loggerinst.warning(
                "You have passed the RHSM username without an associated password. Please provide a password together"
                " with the username."
            )

        if opts["password"] and not opts["username"]:
            loggerinst.warning(
                "You have passed the RHSM password without an associated username. Please provide a username together"
                " with the password."
            )

        # Check if we have duplicate repositories specified
        if opts["enablerepo"] or opts["disablerepo"]:
            duplicate_repos = set(opts["disablerepo"]) & set(opts["enablerepo"])
            if duplicate_repos:
                message = "Duplicate repositories were found across disablerepo and enablerepo options:"
                for repo in duplicate_repos:
                    message += "\n{}".format(repo)
                message += "\nThis ambiguity may have unintended consequences."
                loggerinst.warning(message)

        if opts["no_rhsm"]:
            if not opts["enablerepo"]:
                loggerinst.critical("The --enablerepo option is required when --no-rhsm is used.")
