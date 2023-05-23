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
import os

from convert2rhel import actions
from convert2rhel.pkghandler import compare_package_versions
from convert2rhel.repo import get_hardcoded_repofiles_dir
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)


class IsLoadedKernelLatest(actions.Action):
    id = "IS_LOADED_KERNEL_LATEST"
    # disabling here as some of the return statements would be raised as exceptions in normal code
    # but we don't do that in an Action class
    def run(self):  # pylint: disable= too-many-return-statements
        """Check if the loaded kernel is behind or of the same version as in yum repos."""
        super(IsLoadedKernelLatest, self).run()
        logger.task("Prepare: Check if the loaded kernel version is the most recent")

        if system_info.id == "oracle" and system_info.eus_system:
            logger.info(
                "Skipping the check because there are no publicly available %s %d.%d repositories available."
                % (system_info.name, system_info.version.major, system_info.version.minor)
            )
            return

        cmd = [
            "repoquery",
            "--setopt=exclude=",
            "--quiet",
            "--qf",
            "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}",
        ]

        reposdir = get_hardcoded_repofiles_dir()
        if reposdir and not system_info.has_internet_access:
            logger.warning("Skipping the check as no internet connection has been detected.")
            self.add_message(
                level="WARNING",
                id="IS_LOADED_KERNEL_LATEST_CHECK_SKIP",
                title="Skipping the is loaded kernel latest check",
                description="Skipping the check as no internet connection has been detected.",
            )
            return

        # If the reposdir variable is not empty, meaning that it detected the
        # hardcoded repofiles, we should use that
        # instead of the system repositories located under /etc/yum.repos.d
        if reposdir:
            cmd.append("--setopt=reposdir=%s" % reposdir)

        # For Oracle/CentOS Linux 8 the `kernel` is just a meta package, instead,
        # we check for `kernel-core`. But 7 releases, the correct way to check is
        # using `kernel`.
        package_to_check = "kernel-core" if system_info.version.major >= 8 else "kernel"

        # Append the package name as the last item on the list
        cmd.append(package_to_check)

        # Repoquery failed to detected any kernel or kernel-core packages in it's repositories
        # we allow the user to provide a environment variable to override the functionality and proceed
        # with the conversion, otherwise, we just throw an critical logging to them.
        allow_older_envvar_names = (
            "CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK",
            "CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK",
        )
        # This check is to see which environment variable is set, To allow users in the next version
        # to adjust their environmental variable names. This check will be removed in the future and
        # will only have the 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK' environment variable
        if any(envvar in os.environ for envvar in allow_older_envvar_names):
            if "CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK" in os.environ:
                logger.warning(
                    "You are using the deprecated 'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK'"
                    " environment variable. Please switch to 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK'"
                    " instead."
                )

            logger.warning(
                "Detected 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK' environment variable, we will skip "
                "the %s comparison.\n"
                "Beware, this could leave your system in a broken state." % package_to_check
            )

            self.add_message(
                level="WARNING",
                id="UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK_DETECTED",
                title="Skipping the kernel currency check",
                description=(
                    "Detected 'CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK' environment variable, we will skip "
                    "the %s comparison.\n"
                    "Beware, this could leave your system in a broken state." % package_to_check
                ),
            )
            return

        # Look up for available kernel (or kernel-core) packages versions available
        # in different repositories using the `repoquery` command.  If convert2rhel
        # detects that it is running on a EUS system, then repoquery will use the
        # hardcoded repofiles available under `/usr/share/convert2rhel/repos`,
        # meaning that the tool will fetch only the latest kernels available for
        # that EUS version, and not the most updated version from other newer
        # versions.
        repoquery_output, return_code = run_subprocess(cmd, print_output=False)
        if return_code != 0:
            logger.debug("Got the following output: %s", repoquery_output)
            logger.warning(
                "Couldn't fetch the list of the most recent kernels available in "
                "the repositories. Skipping the loaded kernel check."
            )
            self.add_message(
                level="WARNING",
                id="UNABLE_TO_FETCH_RECENT_KERNELS",
                title="Unable to fetch recent kernels",
                description=(
                    "Couldn't fetch the list of the most recent kernels available in "
                    "the repositories. Skipping the loaded kernel check."
                ),
            )
            return

        packages = []
        # We are expecting a repoquery output to be similar to this:
        #   C2R     1671212820      3.10.0-1160.81.1.el7    updates
        # We need the `C2R` identifier to be present on the line so we can know for
        # sure that the line we are working with is a line that contains
        # relevant repoquery information to our check, otherwise, we just log the
        # information as debug and do nothing with it.
        for line in repoquery_output.split("\n"):
            if line.strip() and "C2R" in line:
                _, build_time, latest_kernel, repoid = tuple(str(line).split("\t"))
                packages.append((build_time, latest_kernel, repoid))
            else:
                # Mainly for debugging purposes to see what is happening if we got
                # anything else that does not have the C2R identifier at the start
                # of the line.
                logger.debug("Got a line without the C2R identifier: %s" % line)

        # If we don't have any packages, then something went wrong, bail out by default
        if not packages:
            self.set_result(
                level="ERROR",
                id="KERNEL_CURRENCY_CHECK_FAIL",
                title="Kernel currency check failed",
                description="Please refer to the diagnosis for further information",
                diagnosis=(
                    "Could not find any %s from repositories to compare against the loaded kernel." % package_to_check
                ),
                remediation=(
                    "Please, check if you have any vendor repositories enabled to proceed with the conversion.\n"
                    "If you wish to ignore this message, set the environment variable "
                    "'CONVERT2RHEL_UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK' to 1."
                ),
            )
            return

        packages.sort(key=lambda x: x[0], reverse=True)
        _, latest_kernel, repoid = packages[0]

        uname_output, _ = run_subprocess(["uname", "-r"], print_output=False)
        loaded_kernel = uname_output.rsplit(".", 1)[0]
        # append the package name to loaded_kernel and latest_kernel so they can be properly processed by
        # compare_package_versions()
        latest_kernel_pkg = "%s-%s" % (package_to_check, latest_kernel)
        loaded_kernel_pkg = "%s-%s" % (package_to_check, loaded_kernel)
        try:
            match = compare_package_versions(latest_kernel_pkg, loaded_kernel_pkg)
        except ValueError as exc:
            self.set_result(
                level="ERROR",
                id="INVALID_KERNEL_PACKAGE",
                title="Invalid kernel package found",
                description="Please refer to the diagnosis for further information",
                diagnosis=str(exc),
            )
            return

        if match != 0:
            repos_message = (
                "in the enabled system repositories"
                if not reposdir
                else "in repositories defined in the %s folder" % reposdir
            )
            self.set_result(
                level="ERROR",
                id="INVALID_KERNEL_VERSION",
                title="Invalid kernel version detected",
                description="The loaded kernel version mismatch the latest one available %s" % repos_message,
                diagnosis=(
                    "The version of the loaded kernel is different from the latest version %s.\n"
                    " Latest kernel version available in %s: %s\n"
                    " Loaded kernel version: %s" % (repos_message, repoid, latest_kernel, loaded_kernel)
                ),
                remediation=(
                    "To proceed with the conversion, update the kernel version by executing the following step:\n\n"
                    "1. yum install %s-%s -y\n"
                    "2. reboot" % (package_to_check, latest_kernel)
                ),
            )
            return

        logger.info("The currently loaded kernel is at the latest version.")
