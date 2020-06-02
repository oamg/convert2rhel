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

import ConfigParser
import os
import re
import logging

from convert2rhel import utils
from convert2rhel.toolopts import tool_opts
from convert2rhel import logger


class SystemInfo(object):

    def __init__(self):
        # Operating system name (e.g. Oracle Linux)
        self.name = None
        # Single-word lowercase identificator of the system (e.g. oracle)
        self.id = None  # pylint: disable=C0103
        # Major version of the operating system (e.g. 6)
        self.version = None
        # Platform architecture
        self.arch = None
        # Fingerprints of the original operating system GPG keys
        self.fingerprints_orig_os = None
        # Fingerprints of RHEL GPG keys available at:
        #  https://access.redhat.com/security/team/key/
        self.fingerprints_rhel = [
            # RHEL 6/7: RPM-GPG-KEY-redhat-release
            "199e2f91fd431d51",
            # RHEL 6/7: RPM-GPG-KEY-redhat-legacy-release
            "5326810137017186",
            # RHEL 6/7: RPM-GPG-KEY-redhat-legacy-former
            "219180cddb42a60e"]
        # Packages to be removed before the system conversion
        self.pkg_blacklist = []
        self.cfg_filename = None
        self.cfg_content = None
        self.system_release_file_content = None
        self.logger = None

    def resolve_system_info(self):
        self.logger = logging.getLogger(__name__)
        self.system_release_file_content = self._get_system_release_file_content()
        self.name = self._get_system_name()
        self.id = self.name.split()[0].lower()
        self.version = self._get_system_version()
        self.arch = self._get_architecture()

        self.cfg_filename = self._get_cfg_filename()
        self.cfg_content = self._get_cfg_content()
        self.pkg_blacklist = self._get_pkg_blacklist()
        self.default_repository_id = self._get_default_repository_id()
        self.fingerprints_orig_os = self._get_gpg_key_fingerprints()
        self._generate_rpm_va()

    @staticmethod
    def _get_system_release_file_content():
        from convert2rhel import redhatrelease
        return redhatrelease.get_system_release_content()

    def _get_system_name(self):
        name = re.search(r"(.+?)\s?(?:release\s?)?\d",
                         self.system_release_file_content).group(1)
        self.logger.info("%-20s %s" % ("Name:", name))
        return name

    def _get_system_version(self):
        version = re.search(r".+?(\d+)\.?",
                            self.system_release_file_content).group(1)

        self.logger.info("%-20s %s" % ("OS major version:", version))
        return version

    def _get_architecture(self):
        arch, _ = utils.run_subprocess("uname -i", print_output=False)
        arch = arch.strip()  # Remove newline
        self.logger.info("%-20s %s" % ("Architecture:", arch))
        return arch

    def _get_cfg_filename(self):
        cfg_filename = "%s-%s-%s.cfg" % (self.id,
                                         self.version,
                                         self.arch)
        self.logger.info("%-20s %s" % ("Config filename:", cfg_filename))
        return cfg_filename

    def _get_cfg_content(self):
        return self._get_cfg_section("system_info")

    def _get_cfg_section(self, section_name):
        """Read out options from within a specific section in a configuration
        file.
        """
        cfg_parser = ConfigParser.ConfigParser()
        cfg_filepath = os.path.join(utils.DATA_DIR, "configs",
                                    self.cfg_filename)
        if not cfg_parser.read(cfg_filepath):
            self.logger.critical("Current combination of system distribution"
                                 " and architecture is not supported for the"
                                 " conversion to RHEL.")

        options_list = cfg_parser.options(section_name)
        return dict(zip(options_list,
                        map(lambda opt: cfg_parser.get(section_name, opt),
                            options_list)))

    def _get_default_repository_id(self):
        return self._get_cfg_opt("default_repository_id")

    def _get_cfg_opt(self, option_name):
        """Return value of a specific configuration file option."""
        if option_name in self.cfg_content:
            return self.cfg_content[option_name]
        else:
            self.logger.error("Internal error: %s option not found in %s"
                              " config file."
                              % (option_name, self.cfg_filename))

    def _get_gpg_key_fingerprints(self):
        return self._get_cfg_opt("gpg_fingerprints").split()

    def _get_pkg_blacklist(self):
        return self._get_cfg_opt("pkg_blacklist").split()

    def _generate_rpm_va(self):
        """Verify the installed files on the system with the rpm metadata
        for debug and support purposes."""
        if tool_opts.no_rpm_va:
            self.logger.info("Skipping execution of 'rpm -Va'.")
            return

        self.logger.info("Running the 'rpm -Va' command which can take several"
                         " minutes. It can be disabled by using the"
                         " --no-rpm-va option.")
        rpm_va, _ = utils.run_subprocess("rpm -Va", print_output=False)
        output_file = os.path.join(logger.LOG_DIR, "rpm_va.log")
        utils.store_content_to_file(output_file, rpm_va)
        self.logger.info("The 'rpm -Va' output has been stored in the %s file"
                         % output_file)


# Code to be executed upon module import
system_info = SystemInfo()  # pylint: disable=C0103
