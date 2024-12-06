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


import os.path

import rpm

from convert2rhel import __file__ as convert2rhel_file
from convert2rhel import __version__ as running_convert2rhel_version
from convert2rhel import actions, exceptions, repo, utils
from convert2rhel.logger import root_logger
from convert2rhel.pkghandler import parse_pkg_string
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import warn_deprecated_env


logger = root_logger.getChild(__name__)

C2R_REPOFILE_URLS = {
    7: "https://cdn-public.redhat.com/content/public/addon/dist/convert2rhel/server/7/7Server/x86_64/files/repofile.repo",
    8: "https://cdn-public.redhat.com/content/public/addon/dist/convert2rhel8/8/x86_64/files/repofile.repo",
    9: "https://cdn-public.redhat.com/content/public/repofiles/convert2rhel-for-rhel-9-x86_64.repo",
}


class Convert2rhelLatest(actions.Action):
    id = "CONVERT2RHEL_LATEST_VERSION"

    def run(self):
        """Make sure that we are running the latest downstream version of convert2rhel"""
        logger.task("Check if this is the latest version of Convert2RHEL")

        super(Convert2rhelLatest, self).run()

        repofile_path = self._download_convert2rhel_repofile()
        if not repofile_path:
            return

        cmd = [
            "repoquery",
            "--releasever={}".format(system_info.version.major),
            "--setopt=reposdir={}".format(os.path.dirname(repofile_path)),
            "--setopt=exclude=",
            "--qf",
            "C2R %{NAME}-%{EPOCH}:%{VERSION}-%{RELEASE}.%{ARCH}",
            "convert2rhel",
        ]

        raw_output_convert2rhel_versions, return_code = utils.run_subprocess(cmd, print_output=False)

        if return_code != 0:
            diagnosis = (
                "Couldn't check if the current installed convert2rhel is the latest version.\n"
                "repoquery failed with the following output:\n{}".format(raw_output_convert2rhel_versions)
            )
            logger.warning(diagnosis)
            self.add_message(
                level="WARNING",
                id="CONVERT2RHEL_LATEST_CHECK_SKIP",
                title="convert2rhel latest version check skip",
                description="Did not perform the convert2hel latest version check",
                diagnosis=diagnosis,
            )
            return

        raw_output_convert2rhel_versions = _extract_convert2rhel_versions(raw_output_convert2rhel_versions)

        latest_available_version = ("0", "0.00", "0")
        convert2rhel_versions = []

        # add each tuple of fields obtained from parse_pkg_string() to convert2rhel_versions
        for raw_pkg in raw_output_convert2rhel_versions:
            try:
                parsed_pkg = parse_pkg_string(raw_pkg)
            except ValueError as exc:
                # Not a valid package string input
                logger.debug(exc)
                continue
            convert2rhel_versions.append(parsed_pkg)

        logger.debug("Found {} convert2rhel package(s)".format(len(convert2rhel_versions)))

        # This loop will determine the latest available convert2rhel version in the yum repo.
        # It assigns the epoch, version, and release ex: ("0", "0.26", "1.el7") to the latest_available_version variable.
        for package_version in convert2rhel_versions:
            # rpm.labelCompare(pkg1, pkg2) compare two package version strings and return
            # -1 if latest_version is greater than package_version, 0 if they are equal, 1 if package_version is greater than latest_version
            ver_compare = rpm.labelCompare(
                (package_version[1], package_version[2], package_version[3]), latest_available_version
            )

            if ver_compare > 0:
                latest_available_version = (package_version[1], package_version[2], package_version[3])

        logger.debug("Found {} to be latest available version".format(latest_available_version[1]))
        precise_available_version = ("0", latest_available_version[1], "0")
        precise_convert2rhel_version = ("0", running_convert2rhel_version, "0")
        # Get source files that we're running with import convert2rhel ; convert2rhel.__file__
        running_convert2rhel_init_file = convert2rhel_file

        # Run `rpm -qf <source file>` to get the installed convert2rhel package NEVRA
        running_convert2rhel_NEVRA, return_code = utils.run_subprocess(
            (
                "rpm",
                "-qf",
                running_convert2rhel_init_file,
                "--qf",
                "C2R %{NAME}-%|EPOCH?{%{EPOCH}}:{0}|:%{VERSION}-%{RELEASE}.%{ARCH}\n",
            ),
            print_output=False,
        )

        running_convert2rhel_NEVRA = _extract_convert2rhel_versions(running_convert2rhel_NEVRA)

        # If we couldn't get a NEVRA above, then print a warning that we could not determine the rpm release and use convert2rhel.__version__ to compare with the latest packaged version
        if return_code != 0 or len(running_convert2rhel_NEVRA) != 1:
            logger.warning(
                "Couldn't determine the rpm release; We will check that the version of convert2rhel ({}) is the latest but ignore the rpm release.".format(
                    running_convert2rhel_version
                )
            )

        else:
            running_convert2rhel_NEVRA = running_convert2rhel_NEVRA[0]
            # Run `rpm -V <convert2rhel pkg NEVRA>` to make sure the user hasn't installed a different convert2rhel version on top of a previously installed rpm package through other means than rpm (e.g. pip install from GitHub)
            _, return_code = utils.run_subprocess(
                ["rpm", "-V", running_convert2rhel_NEVRA],
                print_output=False,
            )

            # If the files aren't what shipped in the rpm, we print a warning that we could not determine the rpm release and use convert2rhel.__version__ to compare with the latest packaged version
            if return_code != 0:
                logger.warning(
                    "Some files in the convert2rhel package have changed so the installed convert2rhel is not what was packaged."
                    " We will check that the version of convert2rhel ({}) is the latest but ignore the rpm release.".format(
                        running_convert2rhel_version
                    )
                )

            # Otherwise use the NEVRA from above to compare with the latest packaged version
            else:
                parsed_convert2rhel_version = parse_pkg_string(running_convert2rhel_NEVRA)

                precise_convert2rhel_version = (
                    parsed_convert2rhel_version[1],
                    parsed_convert2rhel_version[2],
                    parsed_convert2rhel_version[3],
                )

                precise_available_version = latest_available_version

        ver_compare = rpm.labelCompare(precise_convert2rhel_version, precise_available_version)

        formatted_convert2rhel_version = _format_EVR(*precise_convert2rhel_version)
        formatted_available_version = _format_EVR(*precise_available_version)

        if ver_compare < 0:
            warn_deprecated_env("CONVERT2RHEL_ALLOW_OLDER_VERSION")
            if tool_opts.allow_older_version:
                diagnosis = (
                    "You are currently running {} and the latest version of convert2rhel is {}.\n"
                    "You have set the option to allow older convert2rhel version, continuing conversion".format(
                        formatted_convert2rhel_version, formatted_available_version
                    )
                )
                logger.warning(diagnosis)
                self.add_message(
                    level="WARNING",
                    id="ALLOW_OLDER_VERSION_OPTION",
                    title="Outdated convert2rhel version detected",
                    description="An outdated convert2rhel version has been detected",
                    diagnosis=diagnosis,
                )
            else:
                self.set_result(
                    level="OVERRIDABLE",
                    id="OUT_OF_DATE",
                    title="Outdated convert2rhel version detected",
                    description="An outdated convert2rhel version has been detected",
                    diagnosis=(
                        "You are currently running {} and the latest version of convert2rhel is {}.\n"
                        "Only the latest version is supported for conversion.".format(
                            formatted_convert2rhel_version, formatted_available_version
                        )
                    ),
                    remediations="If you want to disregard this check, set the allow_older_version inhibitor"
                    " override in the /etc/convert2rhel.ini config file to true.",
                )
                return

        logger.info("Latest available convert2rhel version is installed.")

    def _download_convert2rhel_repofile(self):
        """Download the official downstream convert2rhel repofile to a temporary directory.

        :return: Path of the downloaded downstream convert2rhel repofile
        :rtype: str
        """
        if system_info.version.major not in C2R_REPOFILE_URLS:
            self.add_message(
                level="WARNING",
                id="CONVERT2RHEL_LATEST_CHECK_UNEXPECTED_SYS_VERSION",
                title="Did not perform convert2rhel latest version check",
                description="Checking whether the installed convert2rhel package is of the latest available version was"
                " skipped due to an unexpected system version.",
                diagnosis="Expected system versions: {}. Detected major version: {}".format(
                    ", ".join(str(x) for x in C2R_REPOFILE_URLS), system_info.version.major
                ),
            )
            return None

        repofile_url = C2R_REPOFILE_URLS[system_info.version.major]
        try:
            client_tools_repofile_path = repo.write_temporary_repofile(repo.download_repofile(repofile_url))
            return client_tools_repofile_path
        except exceptions.CriticalError as err:
            self.add_message(
                level="WARNING",
                id="CONVERT2RHEL_LATEST_CHECK_REPO_DOWNLOAD_FAILED",
                title="Did not perform convert2rhel latest version check",
                description="Checking whether the installed convert2rhel package is of the latest available version was"
                " skipped due to not being able to download the convert2rhel repository file.",
                diagnosis=err.description,
            )
            return None


def _format_EVR(epoch, version, release):
    return "{}".format(version)


def _extract_convert2rhel_versions(raw_versions):
    parsed_versions = []

    # convert the raw output of convert2rhel version strings into a list
    precise_raw_version = raw_versions.splitlines()

    # We are expecting an repoquery output to be similar to this:
    # C2R convert2rhel-0:0.17-1.el7.noarch
    # We need the `C2R` identifier to be present on the line so we can know for
    # sure that the line we are working with is the a line that contains
    # relevant repoquery information to our check, otherwise, we just log the
    # information as debug and do nothing with it.
    for raw_version in precise_raw_version:
        if raw_version.startswith("C2R "):
            parsed_versions.append(raw_version[4:])
        else:
            # Mainly for debugging purposes to see what is happening if we got
            # anything else that does not have the C2R identifier at the start
            # of the line.
            logger.debug("Got a line without the C2R identifier: {}".format(raw_version))
    precise_raw_version = parsed_versions

    return precise_raw_version
