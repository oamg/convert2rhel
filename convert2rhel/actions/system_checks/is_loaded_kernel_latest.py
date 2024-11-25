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


from convert2rhel import actions, repo
from convert2rhel.logger import root_logger
from convert2rhel.pkghandler import compare_package_versions
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import run_subprocess, warn_deprecated_env


logger = root_logger.getChild(__name__)


class IsLoadedKernelLatest(actions.Action):
    id = "IS_LOADED_KERNEL_LATEST"

    # disabling here as some of the return statements would be raised as exceptions in normal code
    # but we don't do that in an Action class
    def run(self):
        """Check if the loaded kernel is behind or of the same version as in yum repos."""
        super(IsLoadedKernelLatest, self).run()
        logger.task("Check if the loaded kernel version is the most recent")

        if system_info.id == "oracle" and system_info.eus_system:
            logger.info(
                "Did not perform the check because there were no publicly available %s %d.%d repositories available."
                % (system_info.name, system_info.version.major, system_info.version.minor)
            )
            return

        # RHELC-884 disable the RHEL repos to avoid reaching them when checking original system.
        repos_to_disable = repo.DisableReposDuringAnalysis().get_rhel_repos_to_disable()
        disable_repo_command = repo.get_rhel_disable_repos_command(repos_to_disable)

        cmd = [
            "repoquery",
            "--setopt=exclude=",
            "--quiet",
        ]
        cmd.extend(disable_repo_command)
        cmd.extend(["--qf", "C2R\\t%{BUILDTIME}\\t%{VERSION}-%{RELEASE}\\t%{REPOID}"])

        # For Oracle/CentOS Linux 8 the `kernel` is just a meta package, instead,
        # we check for `kernel-core`. But 7 releases, the correct way to check is
        # using `kernel`.
        package_to_check = "kernel-core" if system_info.version.major >= 8 else "kernel"

        # Append the package name as the last item on the list
        cmd.append(package_to_check)

        # Repoquery failed to detected any kernel or kernel-core packages in it's repositories
        # we allow the user to provide a environment variable to override the functionality and proceed
        # with the conversion, otherwise, we just throw a critical logging to them.
        warn_deprecated_env("CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK")
        if tool_opts.skip_kernel_currency_check:
            logger.warning(
                "You have set the option to skip the kernel currency check. We will not be checking if the loaded"
                " kernel is of the latest version available.\nBeware, this could leave your system in a broken state."
            )

            self.add_message(
                level="WARNING",
                id="UNSUPPORTED_SKIP_KERNEL_CURRENCY_CHECK_DETECTED",
                title="Did not perform the kernel currency check",
                description="We will not be checking if the loaded kernel is of the latest version available."
                "\nBeware, this could leave your system in a broken state.",
                diagnosis="You have set the option to skip the kernel currency check.",
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
                "the repositories. Did not perform the loaded kernel currency check."
            )
            self.add_message(
                level="WARNING",
                id="UNABLE_TO_FETCH_RECENT_KERNELS",
                title="Unable to fetch recent kernels",
                description=(
                    "Couldn't fetch the list of the most recent kernels available in "
                    "the repositories. Did not perform the loaded kernel currency check."
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
                logger.debug("Got a line without the C2R identifier: {}".format(line))

        # If we don't have any packages, then something went wrong, bail out by default
        if not packages:
            self.set_result(
                level="OVERRIDABLE",
                id="KERNEL_CURRENCY_CHECK_FAIL",
                title="Kernel currency check failed",
                description="Refer to the diagnosis for further information.",
                diagnosis=(
                    "Could not find any {} from repositories to compare against the loaded kernel.".format(
                        package_to_check
                    )
                ),
                remediations=(
                    "Check if you have any vendor repositories enabled to proceed with the conversion.\n"
                    "If you wish to disregard this message, set the skip_kernel_currency_check inhibitor override in"
                    " the /etc/convert2rhel.ini config file to true."
                ),
            )
            return

        packages.sort(key=lambda x: x[0], reverse=True)
        _, latest_kernel, repoid = packages[0]

        uname_output, _ = run_subprocess(["uname", "-r"], print_output=False)
        loaded_kernel = uname_output.rsplit(".", 1)[0]
        # append the package name to loaded_kernel and latest_kernel so they can be properly processed by
        # compare_package_versions()
        latest_kernel_pkg = "{}-{}".format(package_to_check, latest_kernel)
        loaded_kernel_pkg = "{}-{}".format(package_to_check, loaded_kernel)
        try:
            match = compare_package_versions(latest_kernel_pkg, loaded_kernel_pkg)
        except ValueError as exc:
            self.add_message(
                level="WARNING",
                id="INVALID_KERNEL_PACKAGE",
                title="Invalid kernel package found",
                description="Refer to the diagnosis for further information.",
                diagnosis=str(exc),
            )
            return

        if match != 0:
            self.set_result(
                level="OVERRIDABLE",
                id="INVALID_KERNEL_VERSION",
                title="Invalid kernel version detected",
                description="The loaded kernel version mismatch the latest one available in system repositories.",
                diagnosis=(
                    "The version of the loaded kernel is different from the latest version in system repositories. \n"
                    " Latest kernel version available in {}: {}\n"
                    " Loaded kernel version: {}".format(repoid, latest_kernel, loaded_kernel)
                ),
                remediations=(
                    "To proceed with the conversion, update the kernel version by executing the following step:\n\n"
                    "1. yum install {}-{} -y\n"
                    "2. reboot\n"
                    "If you wish to ignore this message, set the skip_kernel_currency_check inhibitor override in"
                    " the /etc/convert2rhel.ini config file to true.".format(package_to_check, latest_kernel)
                ),
            )
            return

        logger.info("The currently loaded kernel is at the latest version.")
