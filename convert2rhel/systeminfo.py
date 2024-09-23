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


import os
import re
import time

from collections import namedtuple

from six.moves import configparser

from convert2rhel import logger, utils
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import run_subprocess
from convert2rhel.utils.rpm import PRE_RPM_VA_LOG_FILENAME


# Number of times to retry checking the status of dbus
CHECK_DBUS_STATUS_RETRIES = 3

# Allowed conversion paths to RHEL. We want to prevent a conversion and minor
# version update at the same time.
RELEASE_VER_MAPPING = {
    "9.10": "9.10",
    "9.9": "9.9",
    "9.8": "9.8",
    "9.7": "9.7",
    "9.6": "9.6",
    "9.5": "9.5",
    "9.4": "9.4",
    "9.3": "9.3",
    "9.2": "9.2",
    "9.1": "9.1",
    "9.0": "9.0",
    "9": "9",  # CentOS Stream and similar
    "8.10": "8.10",
    "8.9": "8.9",
    "8.8": "8.8",
    "8.7": "8.7",
    "8.6": "8.6",
    "8.5": "8.5",
    "8.4": "8.4",
    "8": "8",  # CentOS Stream and similar
    "7.9": "7Server",
}

# Dictionary of EUS minor versions supported and their EUS period start date
EUS_MINOR_VERSIONS = {"8.8": "2023-11-14"}

ELS_RELEASE_DATE = "2024-06-12"


class Version(namedtuple("Version", ["major", "minor"])):
    """
    A namedtuple based class.
    Represents a system version.

    Example:
    >>> ver1 = Version(7, 9)
    >>> ver2 = Version(8, None)
    >>> ver1
    7.9
    >>> repr(ver2)
    '8'
    >>> print(ver1.major, ver1.minor)
    7 9
    """

    def __repr__(self):
        """
        Return a string representation of the version.

        The string is in 'major.minor' format, if minor is None (generally on Stream-like systems)
        return just 'major' version as a string.

        :return: The string representation of the version.
        :rtype: str
        """
        if self.minor:
            return "{major}.{minor}".format(major=self.major, minor=self.minor)

        return "{major}".format(major=self.major)


class SystemInfo:
    def __init__(self):
        # Operating system name (e.g. Oracle Linux)
        self.name = None
        # Single-word lowercase identificator of the system (e.g. oracle)
        self.id = None
        # The optional last part of the distribution name in brackets: "... (Core)" or "... (Oopta)"
        self.distribution_id = None
        # Major and minor version of the operating system (e.g. version.major == 8, version.minor == 7)
        self.version = None
        # Platform architecture
        self.arch = None
        # GPG key IDs of the original operating system GPG keys
        self.key_ids_orig_os = None
        # IDs of GPG keys are available at:
        #  https://access.redhat.com/security/team/key/
        self.key_ids_rhel = [
            # RPM-GPG-KEY-redhat-release
            "199e2f91fd431d51",
            # RPM-GPG-KEY-redhat-legacy-release
            "5326810137017186",
            # RPM-GPG-KEY-redhat-legacy-former
            "219180cddb42a60e",
        ]
        # Whether the system release corresponds to a rhel eus release
        self.eus_system = None
        # Whether the system release corresponds to a rhel els release
        self.els_system = None
        # Packages to be removed before the system conversion
        self.excluded_pkgs = []
        # Packages that need to perform a swap in the transaction
        self.swap_pkgs = {}
        # Release packages to be removed before the system conversion
        self.repofile_pkgs = []
        self.cfg_filename = None
        self.cfg_content = None
        self.system_release_file_content = None
        self.logger = logger.root_logger.getChild(__name__)
        # IDs of the default Red Hat CDN repositories that correspond to the current system
        self.default_rhsm_repoids = None
        # IDs of the Extended Update Support (EUS) Red Hat CDN repositories that correspond to the current system
        self.eus_rhsm_repoids = None
        # IDs of the Extended Lifecycle Support (ELS) Red Hat CDN repositories that correspond to the current system
        self.els_rhsm_repoids = None
        # List of repositories enabled through subscription-manager
        self.submgr_enabled_repos = []
        # Value to use for substituting the $releasever variable in the url of RHEL repositories
        self.releasever = None
        # List of kmods to not inhbit the conversion upon when detected as not available in RHEL
        self.kmods_to_ignore = []
        # Booted kernel VRA (version, release, architecture), e.g. "4.18.0-240.22.1.el8_3.x86_64"
        self.booted_kernel = ""

    def resolve_system_info(self):
        self.system_release_file_content = self.get_system_release_file_content()

        system_release_data = self.parse_system_release_content()
        self.name = system_release_data["name"]
        self.id = system_release_data["id"]
        self.distribution_id = system_release_data["distribution_id"]
        self.version = system_release_data["version"]

        self.arch = self._get_architecture()

        self.cfg_filename = self._get_cfg_filename()
        self.cfg_content = self._get_cfg_content()
        self.excluded_pkgs = self._get_excluded_pkgs()
        self.swap_pkgs = self._get_swap_pkgs()
        self.repofile_pkgs = self._get_repofile_pkgs()
        self.default_rhsm_repoids = self._get_default_rhsm_repoids()
        self.eus_rhsm_repoids = self._get_eus_rhsm_repoids()
        self.els_rhsm_repoids = self._get_els_rhsm_repoids()
        self.key_ids_orig_os = self._get_gpg_key_ids()
        self.generate_rpm_va()
        self.releasever = self._get_releasever()
        self.kmods_to_ignore = self._get_kmods_to_ignore()
        self.booted_kernel = self._get_booted_kernel()
        self.dbus_running = self._is_dbus_running()
        self.eus_system = self.corresponds_to_rhel_eus_release()
        self.els_system = self.corresponds_to_rhel_els_release()

    def print_system_information(self):
        """Print system related information."""
        self.logger.info("%-20s %s" % ("Name:", self.name))
        self.logger.info("%-20s %s" % ("OS version:", self.version))
        self.logger.info("%-20s %s" % ("Architecture:", self.arch))
        self.logger.info("%-20s %s" % ("Config filename:", self.cfg_filename))

    @staticmethod
    def get_system_release_file_content():
        from convert2rhel import redhatrelease

        return redhatrelease.get_system_release_content()

    def parse_system_release_content(self, system_release_content=None):
        """Parse the content of the system release string

        If system_release_content is not provided we use the content from the self.system_release_file_content.

        :param system_release_content: The contents of the system_release file if needed.
        :type system_release_content: str
        :returns: A dictionary containing the system release information
        :rtype: dict[str, str]
        """

        content = self.system_release_file_content if not system_release_content else system_release_content

        matched = re.match(
            # We assume that the /etc/system-release content follows the pattern:
            # "<name> release <full_version> <Beta> (<dist_id>)"
            # Here
            # - <name>, parsed as a named group '(?P<name>.+?)',
            #   is a non-empty string of arbitrary symbols.
            # - "release ", parsed as (?:release\s)?,
            #   is a literal string. It is optional, and it is dropped when parsed, so this group doesn't have a name.
            # - <full_version>, parsed as a named group '(?P<full_version>[.\d]+)',
            #   is a string of arbitrary length containing numbers and dots, for example 8.1.1911 or 7.9.
            #   (For now we do not have examples with version strings containing letters or other symbols)
            # - <Beta>, just the word Beta which may appear in some cases, parsed as '(?:\sBeta)?'.
            # - <dist_id>, parsed as a named group (?P<dist_id>.+), is optional and when it is present, it must appear
            #   in brackets. Thus, the named group is nested under an unnamed group which starts from a space and then
            #   has brackets '(\s\( ...here goes the nested group... \))?'
            #
            # Example:
            #
            #   CentOS Stream release 8
            #   <    name   > <      ><full_version>
            #
            #   CentOS Linux release 8.1.1911        (Core     )
            #   <    name  > <      ><full_version><  <dist_id>>
            #   CentOS Linux release 8.1.1911      Beta       (Core     )
            #   <    name  > <      ><full_version><    ><  <dist_id>>
            r"^(?P<name>.+?)\s(?:release\s)?(?P<full_version>[.\d]+)(?:\sBeta)?(\s\((?P<dist_id>.+)\))?$",
            content,  # type: ignore
        )

        if not matched:
            self.logger.critical_no_exit("Couldn't parse the system release content string: {}".format(content))
            return {}

        name = matched.group("name")
        system_id = name.split()[0].lower()

        distribution_id = matched.group("dist_id")

        full_version = matched.group("full_version")
        version_numbers = full_version.split(".")
        major = int(version_numbers[0])

        # We assume that distributions separate major and minor versions with a dot. If the full_version split by a dot
        # has at least two items - we have a major and minor versions.

        if len(version_numbers) > 1:
            minor = int(version_numbers[1])
        else:
            # In case there are no minor versions specified in the release string, we assume that we are using CentOS
            # Stream or a similar distribution, which is continuously going slightly ahead of the latest released minor
            # version of RHEL up until the end of its lifecycle. Thus, its "ephemeral" minor version is always higher
            # than RHEL X.0-X.9.

            # The Stream lifecycle stops with the RHEL X.10 minor release, when the Stream goes EOL and RHEL catches
            # up with it. Only after that the Stream-like system can be converted to RHEL X.10 without a downgrade.

            # For the Stream conversions we utilize only the major version for specifying the releasever,
            # assuming the rhelX/X/ repository namespace mirrors the latest available rhelX/X.Y/ namespace.
            minor = None

        version = Version(major, minor)

        return {
            "name": name,
            "id": system_id,
            "version": version,
            "distribution_id": distribution_id,
            "full_version": full_version,
        }

    def _get_architecture(self):
        arch, _ = utils.run_subprocess(["uname", "-i"], print_output=False)
        arch = arch.strip()  # Remove newline
        return arch

    def _get_cfg_filename(self):
        cfg_filename = "%s-%d-%s.cfg" % (
            self.id,
            self.version.major,
            self.arch,
        )
        return cfg_filename

    def _get_cfg_content(self):
        return self._get_cfg_section("system_info")

    def _get_cfg_section(self, section_name):
        """Read out options from within a specific section in a configuration
        file.
        """
        cfg_parser = configparser.ConfigParser()
        cfg_filepath = os.path.join(utils.DATA_DIR, "configs", self.cfg_filename)
        if not cfg_parser.read(cfg_filepath):
            self.logger.critical(
                "Current combination of system distribution"
                " and architecture is not supported for the"
                " conversion to RHEL."
            )

        options_list = cfg_parser.options(section_name)
        return dict(
            zip(
                options_list,
                [cfg_parser.get(section_name, opt) for opt in options_list],
            )
        )

    def _get_default_rhsm_repoids(self):
        return self._get_cfg_opt("default_rhsm_repoids").split()

    def _get_eus_rhsm_repoids(self):
        return self._get_cfg_opt("eus_rhsm_repoids").split()

    def _get_els_rhsm_repoids(self):
        return self._get_cfg_opt("els_rhsm_repoids").split()

    def _get_cfg_opt(self, option_name):
        """Return value of a specific configuration file option."""
        if option_name in self.cfg_content:
            return self.cfg_content[option_name]
        else:
            self.logger.error(
                "Internal error: {} option not found in {} config file.".format(option_name, self.cfg_filename)
            )

    def _get_gpg_key_ids(self):
        return self._get_cfg_opt("gpg_key_ids").split()

    def _get_excluded_pkgs(self):
        return self._get_cfg_opt("excluded_pkgs").split()

    def _get_swap_pkgs(self):
        pkgs_to_swap = {}

        try:
            lines = self._get_cfg_opt("swap_pkgs").strip().split("\n")
            for line in lines:
                old_package, new_package = tuple(line.split("|"))

                old_package = old_package.strip()
                new_package = new_package.strip()

                if old_package in pkgs_to_swap:
                    self.logger.warning(
                        "Package {old_package} redefined in swap packages list.\n"
                        "Old package {old_package} will be swapped by {newest_package} instead of {new_package}.".format(
                            old_package=old_package, new_package=pkgs_to_swap[old_package], newest_package=new_package
                        )
                    )
                pkgs_to_swap.update({old_package: new_package})

        except ValueError:
            # Leave the swap packages dict empty, packages for swap aren't defined
            self.logger.debug("Leaving the swap package list empty. No packages defined.")

        except AttributeError:
            # Leave the swap packages dict empty, missing swap_pkgs in config file
            self.logger.warning("Leaving the swap package list empty. Missing swap_pkgs key in configuration file.")

        return pkgs_to_swap

    def _get_repofile_pkgs(self):
        return self._get_cfg_opt("repofile_pkgs").split()

    def _get_releasever(self):
        """
        Get the release version to be passed to yum through --releasever.

        Releasever is used to figure out the version of RHEL that is to be used
        for the conversion, passing the releasever var to yum to it’s --releasever
        option when accessing RHEL repos in the conversion. By default, the value is found by mapping
        from the current distro's version to a compatible version of RHEL via the RELEASE_VER_MAPPING.
        This can be overridden by the user by specifying it in the config file. The version specific
        config files are located in convert2rhel/convert2rhel/data.
        """
        releasever_cfg = self._get_cfg_opt("releasever")
        try:
            # return config value or corresponding releasever from the RELEASE_VER_MAPPING
            return releasever_cfg or RELEASE_VER_MAPPING[repr(self.version)]
        except KeyError:
            self.logger.critical(
                "{os_name} of version {current_version} is not allowed for conversion.\n"
                "Allowed versions are: {allowed_versions}".format(
                    os_name=self.name, current_version=self.version, allowed_versions=list(RELEASE_VER_MAPPING.keys())
                )
            )

    def _get_kmods_to_ignore(self):
        return self._get_cfg_opt("kmods_to_ignore").split()

    def _get_booted_kernel(self):
        kernel_vra = run_subprocess(["uname", "-r"], print_output=False)[0].rstrip()
        self.logger.debug("Booted kernel VRA (version, release, architecture): {0}".format(kernel_vra))
        return kernel_vra

    def generate_rpm_va(self, log_filename=PRE_RPM_VA_LOG_FILENAME):
        """RPM is able to detect if any file installed as part of a package has been changed in any way after the
        package installation.

        Here we are getting a list of changed package files of all the installed packages. Such a list is useful for
        debug and support purposes. It's being saved to the default log folder as log_filename."""
        if tool_opts.no_rpm_va:
            self.logger.info("Skipping the execution of 'rpm -Va'.")
            return

        self.logger.info(
            "Running the 'rpm -Va' command which can take several"
            " minutes. It can be disabled by using the"
            " --no-rpm-va option."
        )
        # Discussed under RHELC-1427, `--nodeps` will skip verification of package dependencies,
        # avoiding unnecessary packages lookup.
        rpm_va, _ = utils.run_subprocess(["rpm", "-Va", "--nodeps"], print_output=False)
        output_file = os.path.join(logger.LOG_DIR, log_filename)
        utils.store_content_to_file(output_file, rpm_va)
        self.logger.info("The 'rpm -Va' output has been stored in the {} file.".format(output_file))

    @staticmethod
    def is_rpm_installed(name):
        _, return_code = run_subprocess(["rpm", "-q", name], print_cmd=False, print_output=False)
        return return_code == 0

    def get_enabled_rhel_repos(self):
        """Get a list of enabled repositories containing RHEL packages.

        This function can return either the repositories enabled through the RHSM tool during the conversion or, if
        the user manually specified the repositories throught the CLI, it will return them based on the
        `tool_opts.enablerepo` option.

        .. note::
            The repositories passed through the CLI have more priority than the ones get get from RHSM.

        :return: A list of enabled repos to use during the conversion
        :rtype: list[str]
        """
        return self.submgr_enabled_repos if not tool_opts.no_rhsm else tool_opts.enablerepo

    def corresponds_to_rhel_eus_release(self):
        """Return whether the current minor version corresponds to a RHEL Extended Update Support (EUS) release.

        For example if we detect CentOS Linux 8.4, the corresponding RHEL 8.4 is an EUS release, but if we detect
        CentOS Linux 8.5, the corresponding RHEL 8.5 is not an EUS release.

        :return: Whether or not the current system has an EUS correspondent in RHEL.
        :rtype: bool
        """
        current_version = repr(self.version)

        if tool_opts.eus and current_version in EUS_MINOR_VERSIONS:
            self.logger.info("EUS argument detected, automatically evaluating system as EUS")
            return True

        return False

    def corresponds_to_rhel_els_release(self):
        """Return whether the current minor version corresponds to a RHEL Extended Lifecycle Support (ELS) release.

        For example if we detect CentOS Linux 7 then this is an ELS release

        :return: Whether or not the current system has an ELS correspondent in RHEL.
        :rtype: bool
        """
        # This check will be dropped once 7 is no longer supported under ELS
        if tool_opts.els and self.version.major == 7:
            return True
        return False

    def _is_dbus_running(self):
        """
        Check whether dbus is running.

        :returns: True if dbus is running.  Otherwise False
        """
        retries = 0
        status = False

        while retries < CHECK_DBUS_STATUS_RETRIES:
            status = is_systemd_managed_service_running("dbus")

            if status is not None:
                # We know that DBus is definitely running or stopped
                break

            # Wait for 1 second, 2 seconds, and then 4 seconds for dbus to be running
            # (In case it was started before convert2rhel but it is slow to start)
            time.sleep(2**retries)
            retries += 1

        else:  # while-else
            # If we haven't gotten a definite yes or no but we've exceeded or retries,
            # report that DBus is not running
            status = False

        return status

    def get_system_release_info(self, system_release_content=None):
        """Return the system release information as a dictionary

        This function aims to retrieve the system release information in a dictionary format.
        This can be used before and after we modify the system-release file on the system,
        as it have a parameter to read from the contents of a system-release file (if called from somewhere else).

        :param system_release_content: The contents of the system_release file if needed.
        :type system_release_content: str
        :returns: A dictionary containing the system release information
        :rtype: dict[str, str]
        """

        release_info = {
            "id": self.distribution_id,
            "name": self.name,
            "version": repr(self.version),
        }

        return release_info


def is_systemd_managed_service_running(service):
    """Get service status from systemd."""
    # Reloading, activating, etc. will return None which means to retry
    running = None

    output, _ = utils.run_subprocess(["/usr/bin/systemctl", "show", "-p", "ActiveState", service], print_output=False)
    for line in output.splitlines():
        # Note: systemctl seems to always emit an ActiveState line (ActiveState=inactive if
        # the service doesn't exist).  So this check is just defensive coding.
        if line.startswith("ActiveState="):
            state = line.split("=", 1)[1]

            if state == "active":
                # service is definitely running
                running = True
                break

            if state in ("inactive", "deactivating", "failed"):
                # service is definitely not running
                running = False
                break

    return running


# Code to be executed upon module import
system_info = SystemInfo()
