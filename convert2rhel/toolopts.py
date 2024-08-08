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

import copy
import logging
import os

from six.moves import configparser

from convert2rhel.utils.subscription import setup_rhsm_parts


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

loggerinst = logging.getLogger(__name__)


class BaseConfig:
    debug = False
    username = None
    config_file = None
    password = None
    no_rhsm = False
    enablerepo = []
    disablerepo = []
    pool = None
    rhsm_hostname = None
    rhsm_port = None
    rhsm_prefix = None
    autoaccept = None
    auto_attach = None
    restart = None
    activation_key = None
    org = None
    arch = None
    no_rpm_va = False
    eus = False
    els = False
    activity = None

    # Settings
    incomplete_rollback = None
    tainted_kernel_module_check_skip = None
    outdated_package_check_skip = None
    allow_older_version = None
    allow_unavailable_kmods = None
    configure_host_metering = None
    skip_kernel_currency_check = None

    def set_opts(self, opts):
        """Set ToolOpts data using dict with values from config file.
        :param opts: Supported options in config file
        """
        for key, value in opts.items():
            if value and hasattr(BaseConfig, key):
                setattr(BaseConfig, key, value)


class FileConfig(BaseConfig):
    def __init__(self, config_files=("~/.convert2rhel.ini", "/etc/convert2rhel.ini")):
        self._config_files = config_files

    def run(self):
        opts = self.options_from_config_files()
        self.set_opts(opts)

    def _normalize_opts(self, opts):
        if opts.get("incomplete_rollback", None):
            self.no_rpm_va = True

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
            raise FileNotFoundError("No such file or directory: %s" % ", ".join(paths))

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
            loggerinst.debug("Checking configuration file at %s" % path)
            # Check for correct permissions on file
            if not oct(os.stat(path).st_mode)[-4:].endswith("00"):
                loggerinst.critical("The %s file must only be accessible by the owner (0600)" % path)

            config_file.read(path)

            # Mapping of all supported options we can have in the config file
            for supported_header, supported_opts in CONFIG_FILE_MAPPING_OPTIONS.items():
                loggerinst.debug("Checking for header '%s'" % supported_header)
                if supported_header not in config_file.sections():
                    loggerinst.warning(
                        "Couldn't find header '%s' in the configuration file %s." % (supported_header, path)
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
            loggerinst.debug("No options found for %s. It seems to be empty or commented." % header)
            return options

        for option in conf_options:
            if option.lower() not in supported_opts:
                loggerinst.warning("Unsupported option '%s' in '%s'" % (option, header))
                continue

            options[option] = config_file.get(header, option).strip('"')
            loggerinst.debug("Found %s in %s" % (option, header))

        return options


class CliConfig(BaseConfig):
    def __init__(self, opts):
        self._opts = opts

    def run(self):
        parts = setup_rhsm_parts(self._opts)

        opts = vars(self._opts)
        opts.update(parts)

        opts = self._normalize_opts(opts)
        self.set_opts(opts)

    def _normalize_opts(self, opts):
        unparsed_opts = copy.copy(opts)
        unparsed_opts["activity"] = _COMMAND_TO_ACTIVITY[opts.pop("command", "convert")]
        unparsed_opts["restart"] = True if unparsed_opts["activity"] == "conversion" else False
        unparsed_opts["disablerepo"] = opts.pop("disablerepo", ["*"])

        return unparsed_opts


class ToolOpts(BaseConfig):
    def __init__(self, config_sources):
        super(ToolOpts, self).__init__()
        for config in reversed(config_sources):
            config.run()


def initialize_toolopts(config_sources):
    global tool_opts
    return ToolOpts(config_sources=config_sources)


tool_opts = None
