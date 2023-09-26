# Copyright(C) 2023 Red Hat, Inc.
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

import itertools
import logging
import os
import re

from functools import cmp_to_key

from convert2rhel import actions, pkghandler
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)

LINK_PREVENT_KMODS_FROM_LOADING = "https://access.redhat.com/solutions/41278"


class RHELKernelModuleNotFound(Exception):
    pass


class EnsureKernelModulesCompatibility(actions.Action):
    id = "ENSURE_KERNEL_MODULES_COMPATIBILITY"
    dependencies = ("SUBSCRIBE_SYSTEM",)

    def _get_loaded_kmods(self):
        """Get a set of kernel modules loaded on host.

        Each module we cut part of the path until the kernel release
        (i.e. /lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz ->
        kernel/lib/a.ko.xz) in order to be able to compare with RHEL
        kernel modules in case of different kernel release
        """
        logger.debug("Getting a list of loaded kernel modules.")
        lsmod_output, _ = run_subprocess(["/usr/sbin/lsmod"], print_output=False)
        modules = re.findall(r"^(\w+)\s.+$", lsmod_output, flags=re.MULTILINE)[1:]
        kernel_modules = [
            self._get_kmod_comparison_key(run_subprocess(["modinfo", "-F", "filename", module], print_output=False)[0])
            for module in modules
        ]
        return set(kernel_modules)

    def _get_rhel_supported_kmods(self):
        """Return set of target RHEL supported kernel modules."""
        basecmd = [
            "repoquery",
            "--releasever=%s" % system_info.releasever,
        ]

        if system_info.version.major >= 8:
            basecmd.append("--setopt=module_platform_id=platform:el" + str(system_info.version.major))

        for repoid in system_info.get_enabled_rhel_repos():
            basecmd.extend(("--repoid", repoid))

        cmd = basecmd[:]
        cmd.append("-f")
        cmd.append("/lib/modules/*.ko*")

        # Without the release package installed, dnf can't determine the
        # modularity platform ID. get output of a command to get all
        # packages which are the source of kmods
        kmod_pkgs_str, _ = run_subprocess(cmd, print_output=False)

        # from these packages we select only the latest one
        kmod_pkgs = self._get_most_recent_unique_kernel_pkgs(kmod_pkgs_str.rstrip("\n").split())
        if not kmod_pkgs:
            logger.debug("Output of the previous repoquery command:\n{0}".format(kmod_pkgs_str))
            raise RHELKernelModuleNotFound(
                "No packages containing kernel modules available in the enabled repositories (%s)."
                % ", ".join(system_info.get_enabled_rhel_repos())
            )

        logger.info(
            "Comparing the loaded kernel modules with the modules available in the following RHEL"
            " kernel packages available in the enabled repositories:\n {0}".format("\n ".join(kmod_pkgs))
        )

        # querying obtained packages for files they produces
        cmd = basecmd[:]
        cmd.append("-l")
        cmd.extend(kmod_pkgs)
        rhel_kmods_str, _ = run_subprocess(cmd, print_output=False)

        return self._get_rhel_kmods_keys(rhel_kmods_str)

    def _get_most_recent_unique_kernel_pkgs(self, pkgs):
        """Return the most recent versions of all kernel packages.

        When we scan kernel modules provided by kernel packages
        it is expensive to check each kernel pkg. Since each new
        kernel pkg do not deprecate kernel modules we only select
        the most recent ones.

        .. note::
            All RHEL kmods packages starts with kernel* or kmod*

        For example, consider the following list of packages::

            list_of_pkgs = [
                'kernel-core-0:4.18.0-240.10.1.el8_3.x86_64',
                'kernel-core-0:4.19.0-240.10.1.el8_3.x86_64',
                'kmod-debug-core-0:4.18.0-240.10.1.el8_3.x86_64',
                'kmod-debug-core-0:4.18.0-245.10.1.el8_3.x86_64
            ]

        And when this function gets called with that same list of packages,
        we have the following output::

            result = get_most_recent_unique_kernel_pkgs(pkgs=list_of_pkgs)
            print(result)
            # (
            #   'kernel-core-0:4.19.0-240.10.1.el8_3.x86_64',
            #   'kmod-debug-core-0:4.18.0-245.10.1.el8_3.x86_64'
            # )

        :param pkgs: A list of package names to be analyzed.
        :type pkgs: list[str]
        :return: A tuple of packages name sorted and normalized
        :rtype: tuple[str]
        """

        pkgs_groups = itertools.groupby(sorted(pkgs), lambda pkg_name: pkg_name.split(":")[0])
        list_of_sorted_pkgs = []
        for distinct_kernel_pkgs in pkgs_groups:
            if distinct_kernel_pkgs[0].startswith(("kernel", "kmod")):
                list_of_sorted_pkgs.append(
                    max(
                        distinct_kernel_pkgs[1],
                        key=cmp_to_key(pkghandler.compare_package_versions),
                    )
                )

        return tuple(list_of_sorted_pkgs)

    def _get_kmod_comparison_key(self, path):
        """Create a comparison key from the kernel module absolute path.

        Converts the path:
            - /lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz -> kernel/lib/a.ko.xz

        .. note:
            The standard kernel modules are located under /lib/modules/{some
            kernel release}/. If we want to make sure that the kernel package
            is present on RHEL, we need to compare the full path, but because
            kernel release might be different, we compare the relative paths
            after kernel release.

        :param path: The complete path to the kernel module being analyzed.
        :type path: str
        """
        return "/".join(path.strip().split("/")[4:])

    def _get_rhel_kmods_keys(self, rhel_kmods_str):
        kernel_module_keys = [
            self._get_kmod_comparison_key(kmod_path)
            for kmod_path in filter(
                lambda path: path.endswith(("ko.xz", "ko")),
                rhel_kmods_str.rstrip("\n").split(),
            )
        ]

        return set(kernel_module_keys)

    def _get_unsupported_kmods(self, host_kmods, rhel_supported_kmods):
        """
        Return a set of full paths to those installed kernel modules that are
        not available in RHEL repositories.

        Ignore certain kmods mentioned in the system configs. These kernel
        modules moved to kernel core, meaning that the functionality is
        retained and we would be incorrectly saying that the modules are not
        supported in RHEL.
        """
        unsupported_kmods_subpaths = host_kmods - rhel_supported_kmods - set(system_info.kmods_to_ignore)
        unsupported_kmods_full_paths = [
            "/lib/modules/{kver}/{kmod}".format(kver=system_info.booted_kernel, kmod=kmod)
            for kmod in unsupported_kmods_subpaths
        ]
        return unsupported_kmods_full_paths

    def run(self):
        """Ensure that the host kernel modules are compatible with RHEL."""
        super(EnsureKernelModulesCompatibility, self).run()

        logger.task("Prepare: Ensure kernel modules compatibility with RHEL")

        try:
            host_kmods = self._get_loaded_kmods()
            rhel_supported_kmods = self._get_rhel_supported_kmods()
            unsupported_kmods = self._get_unsupported_kmods(host_kmods, rhel_supported_kmods)

            # Check if we have the environment variable set, if we do, send a
            # warning and return.
            if "CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS" in os.environ:
                logger.warning(
                    "Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable."
                    " We will continue the conversion with the following kernel modules unavailable in RHEL:\n"
                    "{kmods}\n".format(kmods="\n".join(unsupported_kmods))
                )
                self.add_message(
                    level="WARNING",
                    id="ALLOW_UNAVAILABLE_KERNEL_MODULES",
                    title="Skipping the ensure kernel modules compatibility check",
                    description="Detected 'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS' environment variable.",
                    diagnosis="We will continue the conversion with the following kernel modules unavailable in RHEL:\n"
                    "{kmods}\n".format(kmods="\n".join(unsupported_kmods)),
                )
                return

            # If there is any unsupported kmods found, set the result to overridable
            if unsupported_kmods:
                self.set_result(
                    level="OVERRIDABLE",
                    id="UNSUPPORTED_KERNEL_MODULES",
                    title="Unsupported kernel modules",
                    description="Unsupported kernel modules were found",
                    diagnosis="The following loaded kernel modules are not available in RHEL:\n{0}\n".format(
                        "\n".join(unsupported_kmods)
                    ),
                    remediation="Ensure you have updated the kernel to the latest available version and rebooted the system.\nIf this "
                    "message persists, you can prevent the modules from loading by following {0} and rerun convert2rhel.\n"
                    "Keeping them loaded could cause the system to malfunction after the conversion as they might not work "
                    "properly with the RHEL kernel.\n"
                    "To circumvent this check and accept the risk you can set environment variable "
                    "'CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS=1'.".format(LINK_PREVENT_KMODS_FROM_LOADING),
                )
                return

            logger.debug("All loaded kernel modules are available in RHEL.")
        except RHELKernelModuleNotFound as e:
            self.set_result(
                level="ERROR",
                id="NO_RHEL_KERNEL_MODULES_FOUND",
                title="No RHEL kernel modules were found",
                description="This check was unable to find any kernel modules in the packages in the enabled yum repositories.",
                diagnosis=str(e),
                remediation="Adding additional repositories to those mentioned in the diagnosis may solve this issue.",
            )
        except ValueError as e:
            self.set_result(
                level="ERROR",
                id="CANNOT_COMPARE_PACKAGE_VERSIONS",
                title="Error while comparing packages",
                description="There was an error while detecting the kernel package which corresponds to the kernel modules present on the system.",
                diagnosis="Package comparison failed: %s" % e,
            )
