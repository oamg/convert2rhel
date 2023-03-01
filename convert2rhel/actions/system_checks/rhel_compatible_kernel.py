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

import logging

from convert2rhel import actions
from convert2rhel.pkghandler import get_installed_pkg_information, get_installed_pkg_objects
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)

# The kernel version stays the same throughout a RHEL major version
COMPATIBLE_KERNELS_VERS = {
    7: "3.10.0",
    8: "4.18.0",
}
BAD_KERNEL_RELEASE_SUBSTRINGS = ("uek", "rt", "linode")


class RhelCompatibleKernel(actions.Action):
    id = "RHEL_COMPATIBLE_KERNEL"

    def run(self):
        """Ensure the booted kernel is signed, is standard (not UEK, realtime, ...), and has the same version as in RHEL.
        By requesting that, we can be confident that the RHEL kernel will provide the same capabilities as on the
        original system.
        """
        super(RhelCompatibleKernel, self).run()
        logger.task("Prepare: Check kernel compatibility with RHEL")
        if any(
            (
                _bad_kernel_version(system_info.booted_kernel),
                _bad_kernel_package_signature(system_info.booted_kernel),
                _bad_kernel_substring(system_info.booted_kernel),
            )
        ):
            self.set_result(
                status="ERROR",
                error_id="BOOTED_KERNEL_INCOMPATIBLE",
                message=(
                    "The booted kernel version is incompatible with the standard RHEL kernel. "
                    "To proceed with the conversion, boot into a kernel that is available in the {0} {1} base repository"
                    " by executing the following steps:\n\n"
                    "1. Ensure that the {0} {1} base repository is enabled\n"
                    "2. Run: yum install kernel\n"
                    "3. (optional) Run: grubby --set-default "
                    '/boot/vmlinuz-`rpm -q --qf "%{{BUILDTIME}}\\t%{{EVR}}.%{{ARCH}}\\n" kernel | sort -nr | head -1 | cut -f2`\n'
                    "4. Reboot the machine and if step 3 was not applied choose the kernel"
                    " installed in step 2 manually".format(system_info.name, system_info.version.major)
                ),
            )
            return
        else:
            logger.info("The booted kernel %s is compatible with RHEL." % system_info.booted_kernel)


def _bad_kernel_version(kernel_release):
    """Return True if the booted kernel version does not correspond to the kernel version available in RHEL."""
    kernel_version = kernel_release.split("-")[0]
    try:
        incompatible_version = COMPATIBLE_KERNELS_VERS[system_info.version.major] != kernel_version
        if incompatible_version:
            logger.warning(
                "Booted kernel version '%s' does not correspond to the version "
                "'%s' available in RHEL %d"
                % (
                    kernel_version,
                    COMPATIBLE_KERNELS_VERS[system_info.version.major],
                    system_info.version.major,
                )
            )
        else:
            logger.debug(
                "Booted kernel version '%s' corresponds to the version available in RHEL %d"
                % (kernel_version, system_info.version.major)
            )
        return incompatible_version
    except KeyError:
        logger.debug("Unexpected OS major version. Expected: %r" % COMPATIBLE_KERNELS_VERS.keys())
        return True


def _bad_kernel_package_signature(kernel_release):
    """Return True if the booted kernel is not signed by the original OS vendor, i.e. it's a custom kernel."""
    vmlinuz_path = "/boot/vmlinuz-%s" % kernel_release

    kernel_pkg, return_code = run_subprocess(
        ["rpm", "-qf", "--qf", "%{VERSION}&%{RELEASE}&%{ARCH}&%{NAME}", vmlinuz_path], print_output=False
    )

    os_vendor = system_info.name.split()[0]
    if return_code == 1:
        logger.warning(
            "The booted kernel %s is not owned by any installed package."
            " It needs to be owned by a package signed by %s." % (vmlinuz_path, os_vendor)
        )

        return True

    version, release, arch, name = tuple(kernel_pkg.split("&"))
    logger.debug("Booted kernel package name: {0}".format(name))

    kernel_pkg_obj = get_installed_pkg_objects(name, version, release, arch)[0]
    package = get_installed_pkg_information(str(kernel_pkg_obj))[0]
    bad_signature = system_info.cfg_content["gpg_fingerprints"] != package.fingerprint

    # e.g. Oracle Linux Server -> Oracle or
    #      Oracle Linux Server -> CentOS Linux
    if bad_signature:
        logger.warning("Custom kernel detected. The booted kernel needs to be signed by %s." % os_vendor)
        return True

    logger.debug("The booted kernel is signed by %s." % os_vendor)
    return False


def _bad_kernel_substring(kernel_release):
    """Return True if the booted kernel release contains one of the strings that identify it as non-standard kernel."""
    bad_substring = any(bad_substring in kernel_release for bad_substring in BAD_KERNEL_RELEASE_SUBSTRINGS)
    if bad_substring:
        logger.debug(
            "The booted kernel '{0}' contains one of the disallowed "
            "substrings: {1}".format(kernel_release, BAD_KERNEL_RELEASE_SUBSTRINGS)
        )
        return True
    return False
