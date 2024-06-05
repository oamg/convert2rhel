# Copyright(C) 2024 Red Hat, Inc.
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

import glob
import logging
import os
import re

from convert2rhel import actions, pkghandler, pkgmanager, utils
from convert2rhel.systeminfo import system_info


loggerinst = logging.getLogger(__name__)


class InstallRhelKernel(actions.Action):
    id = "INSTALL_RHEL_KERNEL"
    dependencies = ("CONVERT_SYSTEM_PACKAGES",)

    def run(self):
        """Install and update the RHEL kernel."""
        super(InstallRhelKernel, self).run()

        loggerinst.info("Installing RHEL kernel ...")
        output, ret_code = pkgmanager.call_yum_cmd(command="install", args=["kernel"])
        kernel_update_needed = False

        if ret_code != 0:
            self.set_result(
                level="ERROR",
                id="FAILED_TO_INSTALL_RHEL_KERNEL",
                title="Failed to install RHEL kernel",
                description="There was an error while attempting to install the RHEL kernel from yum.",
                remediations="Please check that you can access the repositories that provide the RHEL kernel.",
            )
            return

        # Check if kernel with same version is already installed.
        # Example output from yum and dnf:
        #  "Package kernel-4.18.0-193.el8.x86_64 is already installed."
        already_installed = re.search(r" (.*?)(?: is)? already installed", output, re.MULTILINE)
        if already_installed:
            rhel_kernel_nevra = already_installed.group(1)
            non_rhel_kernels = pkghandler.get_installed_pkgs_w_different_fingerprint(
                system_info.fingerprints_rhel, "kernel"
            )
            for non_rhel_kernel in non_rhel_kernels:
                # We're comparing to NEVRA since that's what yum/dnf prints out
                if rhel_kernel_nevra == pkghandler.get_pkg_nevra(non_rhel_kernel):
                    # If the installed kernel is from a third party (non-RHEL) and has the same NEVRA as the one available
                    # from RHEL repos, it's necessary to install an older version RHEL kernel and the third party one will
                    # be removed later in the conversion process. It's because yum/dnf is unable to reinstall a kernel.
                    info_message = (
                        "Conflict of kernels: One of the installed kernels"
                        " has the same version as the latest RHEL kernel."
                    )
                    loggerinst.info("\n%s" % info_message)
                    self.add_message(level="INFO", id="CONFLICT_OF_KERNELS", description=info_message)
                    pkghandler.handle_no_newer_rhel_kernel_available()
                    kernel_update_needed = True
        if kernel_update_needed:
            pkghandler.update_rhel_kernel()


class VerifyRhelKernelInstalled(actions.Action):
    id = "VERIFY_RHEL_KERNEL_INSTALLED"
    dependencies = ("INSTALL_RHEL_KERNEL",)

    def run(self):
        """Verify that the RHEL kernel has been successfully installed and raise an ERROR if not"""
        super(VerifyRhelKernelInstalled, self).run()

        loggerinst.info("Verifying that RHEL kernel has been installed")
        if not pkghandler.is_rhel_kernel_installed():
            self.set_result(
                level="ERROR",
                id="NO_RHEL_KERNEL_INSTALLED",
                title="No RHEL kernel installed",
                description="There is no RHEL kernel installed on the system.",
                remediations="Verify that the repository used for installing kernel contains RHEL packages.",
            )
            return

        loggerinst.info("RHEL kernel has been installed.")
        self.add_message(
            level="INFO",
            id="RHEL_KERNEL_INSTALLED",
            title="RHEL kernel installed",
            description="The RHEL kernel has been installed successfully.",
        )


class FixInvalidGrub2Entries(actions.Action):
    id = "FIX_INVALID_GRUB2_ENTRIES"
    dependencies = ("KERNEL_PACKAGES_INSTALLATION",)

    def run(self):
        """
        On systems derived from RHEL 8 and later, /etc/machine-id is being used to identify grub2 boot loader entries per
        the Boot Loader Specification.
        However, at the time of executing convert2rhel, the current machine-id can be different from the machine-id from the
        time when the kernels were installed. If that happens:
        - convert2rhel installs the RHEL kernel, but it's not set as default
        - convert2rhel removes the original OS kernels, but for these the boot entries are not removed
        The solution handled by this function is to remove the non-functioning boot entries upon the removal of the original
        OS kernels, and set the RHEL kernel as default.
        """
        super(FixInvalidGrub2Entries, self).run()

        if system_info.version.major < 8:
            # Applicable only on systems derived from RHEL 8 and later, and systems using GRUB2 (s390x uses zipl)
            return

        loggerinst.info("Fixing GRUB boot loader entries.")

        machine_id = utils.get_file_content("/etc/machine-id").strip()
        boot_entries = glob.glob("/boot/loader/entries/*.conf")
        for entry in boot_entries:
            # The boot loader entries in /boot/loader/entries/<machine-id>-<kernel-version>.conf
            if machine_id not in os.path.basename(entry):
                loggerinst.debug("Removing boot entry %s" % entry)
                os.remove(entry)

        # Removing a boot entry that used to be the default makes grubby to choose a different entry as default, but we will
        # call grub --set-default to set the new default on all the proper places, e.g. for grub2-editenv
        output, ret_code = utils.run_subprocess(["/usr/sbin/grubby", "--default-kernel"], print_output=False)
        if ret_code:
            # Not setting the default entry shouldn't be a deal breaker and the reason to stop the conversions, grub should
            # pick one entry in any case.
            loggerinst.warning("Couldn't get the default GRUB2 boot loader entry:\n%s" % output)
            self.add_message(
                level="WARNING",
                id="UNABLE_TO_GET_GRUB2_BOOT_LOADER_ENTRY",
                title="Unable to get the GRUB2 boot loader entry",
                description="Couldn't get the default GRUB2 boot loader entry:\n%s" % output,
            )
            return
        loggerinst.debug("Setting RHEL kernel %s as the default boot loader entry." % output.strip())
        output, ret_code = utils.run_subprocess(["/usr/sbin/grubby", "--set-default", output.strip()])
        if ret_code:
            loggerinst.warning("Couldn't set the default GRUB2 boot loader entry:\n%s" % output)
            self.add_message(
                level="WARNING",
                id="UNABLE_TO_SET_GRUB2_BOOT_LOADER_ENTRY",
                title="Unable to set the GRUB2 boot loader entry",
                description="Couldn't set the default GRUB2 boot loader entry:\n%s" % output,
            )


class FixDefaultKernel(actions.Action):
    id = "FIX_DEFAULT_KERNEL"
    dependencies = ("FIX_INVALID_GRUB2_ENTRIES",)

    def run(self):
        """
        Systems converted from Oracle Linux or CentOS Linux may have leftover kernel-uek or kernel-plus in
        /etc/sysconfig/kernel as DEFAULTKERNEL.
        This function fixes that by replacing the DEFAULTKERNEL setting from kernel-uek or kernel-plus to kernel for
        RHEL7 and kernel-core for RHEL8.
        """
        super(FixDefaultKernel, self).run()

        loggerinst = logging.getLogger(__name__)

        loggerinst.info("Checking for incorrect boot kernel")
        kernel_sys_cfg = utils.get_file_content("/etc/sysconfig/kernel")

        possible_kernels = ["kernel-uek", "kernel-plus"]
        kernel_to_change = next(
            iter(kernel for kernel in possible_kernels if kernel in kernel_sys_cfg),
            None,
        )
        if kernel_to_change:
            loggerinst.warning("Detected leftover boot kernel, changing to RHEL kernel")
            self.add_message(
                level="WARNING",
                id="LEFTOVER_BOOT_KERNEL_DETECTED",
                title="Leftover boot kernel detected",
                description="Detected leftover boot kernel, changing to RHEL kernel",
            )
            # need to change to "kernel" in rhel7 and "kernel-core" in rhel8
            new_kernel_str = "DEFAULTKERNEL=" + ("kernel" if system_info.version.major == 7 else "kernel-core")

            kernel_sys_cfg = kernel_sys_cfg.replace("DEFAULTKERNEL=" + kernel_to_change, new_kernel_str)
            utils.store_content_to_file("/etc/sysconfig/kernel", kernel_sys_cfg)
            loggerinst.info("Boot kernel %s was changed to %s" % (kernel_to_change, new_kernel_str))
        else:
            loggerinst.debug("Boot kernel validated.")


class KernelPkgsInstall(actions.Action):
    id = "KERNEL_PACKAGES_INSTALLATION"
    dependencies = ("VERIFY_RHEL_KERNEL_INSTALLED",)

    def run(self):
        """Install kernel packages and remove non-RHEL kernels."""
        super(KernelPkgsInstall, self).run()

        kernel_pkgs_to_install = pkghandler.remove_non_rhel_kernels()
        if kernel_pkgs_to_install:
            pkghandler.install_additional_rhel_kernel_pkgs(kernel_pkgs_to_install)
