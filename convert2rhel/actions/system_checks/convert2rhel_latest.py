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

import logging
import os.path
import shutil
import tempfile

import rpm

from convert2rhel import __file__ as convert2rhel_file
from convert2rhel import __version__ as running_convert2rhel_version
from convert2rhel import actions, utils
from convert2rhel.pkghandler import parse_pkg_string
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import files


logger = logging.getLogger(__name__)

# The SSL certificate of the https://cdn.redhat.com/ server
SSL_CERT_PATH = os.path.join(utils.DATA_DIR, "redhat-uep.pem")
CDN_URL = "https://cdn.redhat.com/content/public/convert2rhel/$releasever/$basearch/os/"
RPM_GPG_KEY_PATH = os.path.join(utils.DATA_DIR, "gpg-keys", "RPM-GPG-KEY-redhat-release")

CONVERT2RHEL_REPO_CONTENT = """\
[convert2rhel]
name=Convert2RHEL Repository
baseurl=%s
gpgcheck=1
enabled=1
sslcacert=%s
gpgkey=file://%s""" % (
    CDN_URL,
    SSL_CERT_PATH,
    RPM_GPG_KEY_PATH,
)


class Convert2rhelLatest(actions.Action):
    id = "CONVERT2RHEL_LATEST_VERSION"

    def run(self):
        """Make sure that we are running the latest downstream version of convert2rhel"""
        logger.task("Prepare: Check if this is the latest version of Convert2RHEL")

        super(Convert2rhelLatest, self).run()

        repo_dir = tempfile.mkdtemp(prefix="convert2rhel_repo.", dir=utils.TMP_DIR)
        repo_path = os.path.join(repo_dir, "convert2rhel.repo")
        utils.store_content_to_file(filename=repo_path, content=CONVERT2RHEL_REPO_CONTENT)

        cmd = [
            "repoquery",
            "--disablerepo=*",
            "--enablerepo=convert2rhel",
            "--releasever=%s" % system_info.version.major,
            "--setopt=reposdir=%s" % repo_dir,
            "--qf",
            "C2R %{NAME}-%{EPOCH}:%{VERSION}-%{RELEASE}.%{ARCH}",
            "convert2rhel",
        ]

        # Note: This is safe because we're creating in utils.TMP_DIR which is hardcoded to
        # /var/lib/convert2rhel which does not have any world-writable directory components.
        files.mkdir_p(repo_dir)

        try:
            raw_output_convert2rhel_versions, return_code = utils.run_subprocess(cmd, print_output=False)
        finally:
            shutil.rmtree(repo_dir)

        if return_code != 0:
            diagnosis = (
                "Couldn't check if the current installed convert2rhel is the latest version.\n"
                "repoquery failed with the following output:\n%s" % (raw_output_convert2rhel_versions)
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

        logger.debug("Found %s convert2rhel package(s)" % len(convert2rhel_versions))

        # This loop will determine the latest available convert2rhel version in the yum repo.
        # It assigns the epoch, version, and release ex: ("0", "0.26", "1.el7") to the latest_available_version variable.
        for package_version in convert2rhel_versions:
            logger.debug("...comparing version %s" % latest_available_version[1])
            # rpm.labelCompare(pkg1, pkg2) compare two package version strings and return
            # -1 if latest_version is greater than package_version, 0 if they are equal, 1 if package_version is greater than latest_version
            ver_compare = rpm.labelCompare(
                (package_version[1], package_version[2], package_version[3]), latest_available_version
            )

            if ver_compare > 0:
                logger.debug(
                    "...found %s to be newer than %s, updating" % (package_version[2], latest_available_version[1])
                )
                latest_available_version = (package_version[1], package_version[2], package_version[3])

        logger.debug("Found %s to be latest available version" % (latest_available_version[1]))
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
                "Couldn't determine the rpm release; We will check that the version of convert2rhel (%s) is the latest but ignore the rpm release."
                % running_convert2rhel_version
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
                    " We will check that the version of convert2rhel (%s) is the latest but ignore the rpm release."
                    % running_convert2rhel_version
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
            if "CONVERT2RHEL_ALLOW_OLDER_VERSION" in os.environ:
                diagnosis = (
                    "You are currently running %s and the latest version of convert2rhel is %s.\n"
                    "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion"
                    % (formatted_convert2rhel_version, formatted_available_version)
                )
                logger.warning(diagnosis)
                self.add_message(
                    level="WARNING",
                    id="ALLOW_OLDER_VERSION_ENVIRONMENT_VARIABLE",
                    title="Outdated convert2rhel version detected",
                    description="An outdated convert2rhel version has been detected",
                    diagnosis=diagnosis,
                )
            else:
                if int(system_info.version.major) <= 6:
                    logger.warning(
                        "You are currently running %s and the latest version of convert2rhel is %s.\n"
                        "We encourage you to update to the latest version."
                        % (formatted_convert2rhel_version, formatted_available_version)
                    )
                    self.add_message(
                        level="WARNING",
                        id="OUTDATED_CONVERT2RHEL_VERSION",
                        title="Outdated convert2rhel version detected",
                        description="An outdated convert2rhel version has been detected",
                        diagnosis=(
                            "You are currently running %s and the latest version of convert2rhel is %s.\n"
                            "We encourage you to update to the latest version."
                            % (formatted_convert2rhel_version, formatted_available_version)
                        ),
                    )

                else:
                    self.set_result(
                        level="ERROR",
                        id="OUT_OF_DATE",
                        title="Outdated convert2rhel version detected",
                        description="An outdated convert2rhel version has been detected",
                        diagnosis=(
                            "You are currently running %s and the latest version of convert2rhel is %s.\n"
                            "Only the latest version is supported for conversion."
                            % (formatted_convert2rhel_version, formatted_available_version)
                        ),
                        remediations="If you want to disregard this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue.",
                    )
                    return

        logger.info("Latest available convert2rhel version is installed.")


def _format_EVR(epoch, version, release):
    return "%s" % (version)


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
            logger.debug("Got a line without the C2R identifier: %s" % raw_version)
    precise_raw_version = parsed_versions

    return precise_raw_version
