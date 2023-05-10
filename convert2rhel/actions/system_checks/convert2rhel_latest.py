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

from convert2rhel import __version__ as installed_convert2rhel_version
from convert2rhel import actions, utils
from convert2rhel.pkghandler import parse_pkg_string
from convert2rhel.systeminfo import system_info


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

        if not system_info.has_internet_access:
            logger.warning("Skipping the check because no internet connection has been detected.")
            self.add_message(
                level="WARNING",
                id="CONVERT2RHEL_LATEST_CHECK_SKIP_NO_INTERNET",
                message="Skipping the check because no internet connection has been detected.",
            )
            return

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
        utils.mkdir_p(repo_dir)

        try:
            raw_output_convert2rhel_versions, return_code = utils.run_subprocess(cmd, print_output=False)
        finally:
            shutil.rmtree(repo_dir)

        if return_code != 0:
            logger.warning(
                "Couldn't check if the current installed Convert2RHEL is the latest version.\n"
                "repoquery failed with the following output:\n%s" % (raw_output_convert2rhel_versions)
            )
            self.add_message(
                level="WARNING",
                id="CONVERT2RHEL_LATEST_CHECK_SKIP",
                message=(
                    "Couldn't check if the current installed Convert2RHEL is the latest version.\n"
                    "repoquery failed with the following output:\n%s" % (raw_output_convert2rhel_versions)
                ),
            )
            return

        # convert the raw output of convert2rhel version strings into a list
        raw_output_convert2rhel_versions = raw_output_convert2rhel_versions.splitlines()

        temp_raw_output = []

        # We are expecting an repoquery output to be similar to this:
        # C2R convert2rhel-0:0.17-1.el7.noarch
        # We need the `C2R` identifier to be present on the line so we can know for
        # sure that the line we are working with is the a line that contains
        # relevant repoquery information to our check, otherwise, we just log the
        # information as debug and do nothing with it.
        for raw_version in raw_output_convert2rhel_versions:
            if "C2R" in raw_version:
                temp_raw_output.append(raw_version.lstrip("C2R "))
            else:
                # Mainly for debugging purposes to see what is happening if we got
                # anything else that does not have the C2R identifier at the start
                # of the line.
                logger.debug("Got a line without the C2R identifier: %s" % raw_version)
        raw_output_convert2rhel_versions = temp_raw_output

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
        # After the for loop, the latest_available_version variable will gain the epoch, version, and release
        # (e.g. ("0" "0.26" "1.el7")) information from the Convert2RHEL yum repo
        # when the versions are the same the latest_available_version's release field will cause it to evaluate as a later version.
        # Therefore we need to hardcode "0" for both the epoch and release below for installed_convert2rhel_version
        # and latest_available_version respectively, to compare **just** the version field.
        ver_compare = rpm.labelCompare(
            ("0", installed_convert2rhel_version, "0"), ("0", latest_available_version[1], "0")
        )
        if ver_compare < 0:
            # Current and deprecated env var names
            allow_older_envvar_names = ("CONVERT2RHEL_ALLOW_OLDER_VERSION", "CONVERT2RHEL_UNSUPPORTED_VERSION")
            if any(envvar in os.environ for envvar in allow_older_envvar_names):
                if "CONVERT2RHEL_ALLOW_OLDER_VERSION" not in os.environ:
                    logger.warning(
                        "You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_VERSION'"
                        " environment variable.  Please switch to 'CONVERT2RHEL_ALLOW_OLDER_VERSION'"
                        " instead."
                    )
                    self.add_message(
                        level="WARNING",
                        id="DEPRECATED_ENVIRONMENT_VARIABLE",
                        message=(
                            "You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_VERSION'"
                            " environment variable.  Please switch to 'CONVERT2RHEL_ALLOW_OLDER_VERSION'"
                            " instead."
                        ),
                    )
                logger.warning(
                    "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
                    "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion"
                    % (installed_convert2rhel_version, latest_available_version[1])
                )
                self.add_message(
                    level="WARNING",
                    id="ALLOW_OLDER_VERSION_ENVIRONMENT_VARIABLE",
                    message=(
                        "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
                        "'CONVERT2RHEL_ALLOW_OLDER_VERSION' environment variable detected, continuing conversion"
                        % (installed_convert2rhel_version, latest_available_version[1])
                    ),
                )

            else:
                if int(system_info.version.major) <= 6:
                    logger.warning(
                        "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
                        "We encourage you to update to the latest version."
                        % (installed_convert2rhel_version, latest_available_version[1])
                    )
                    self.add_message(
                        level="WARNING",
                        id="OUTDATED_CONVERT2RHEL_VERSION",
                        message=(
                            "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
                            "We encourage you to update to the latest version."
                            % (installed_convert2rhel_version, latest_available_version[1])
                        ),
                    )

                else:
                    self.set_result(
                        level="ERROR",
                        id="OUT_OF_DATE",
                        message=(
                            "You are currently running %s and the latest version of Convert2RHEL is %s.\n"
                            "Only the latest version is supported for conversion. If you want to ignore"
                            " this check, then set the environment variable 'CONVERT2RHEL_ALLOW_OLDER_VERSION=1' to continue."
                            % (installed_convert2rhel_version, latest_available_version[1])
                        ),
                    )
                    return

        logger.info("Latest available Convert2RHEL version is installed.")
