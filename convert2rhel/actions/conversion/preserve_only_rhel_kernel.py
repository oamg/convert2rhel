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
import os

from convert2rhel import actions, logger, pkghandler, pkgmanager, utils
from convert2rhel.systeminfo import system_info


_kernel_update_needed = None

loggerinst = logger.root_logger.getChild(__name__)


class InstallRhelKernel(actions.Action):
    id = "INSTALL_RHEL_KERNEL"
    dependencies = ("CONVERT_SYSTEM_PACKAGES",)

    def run(self):
        """Install and update the RHEL kernel."""
        super(InstallRhelKernel, self).run()
        loggerinst.task("Convert: Prepare kernel")

        rhel_kernels = pkghandler.get_installed_pkgs_by_key_id(system_info.key_ids_rhel, name="kernel")

        if not rhel_kernels:
            # install the rhel kernel when any isn't installed
            loggerinst.debug("handle_no_newer_rhel_kernel_available")
            pkghandler.handle_no_newer_rhel_kernel_available()

        """
        # Solution for RHELC-1707
        # Update is needed in the UpdateKernel action
        global _kernel_update_needed

        loggerinst.info("Installing RHEL kernel ...")
        output, ret_code = pkgmanager.call_yum_cmd(command="install", args=["kernel"])
        _kernel_update_needed = False

        if ret_code != 0:
            self.set_result(
                level="ERROR",
                id="FAILED_TO_INSTALL_RHEL_KERNEL",
                title="Failed to install RHEL kernel",
                description="There was an error while attempting to install the RHEL kernel from yum.",
                remediations="Please check that you can access the repositories that provide the RHEL kernel.",
            )
            return

        ## new code

        # installed_kernel, available_kernel = pkghandler.get_kernel_availability()

        # TODO check statement bellow
        # at this moment we should have access only to rhel content, any original vendor repos available at this moment
        # this should return latest available kernel installed
        cmd = ["repoquery", "kernel"]
        target_kernel = utils.run_subprocess(cmd)

        # Get list of kernel pkgs not signed by Red Hat
        non_rhel_kernels_pkg_info = pkghandler.get_installed_pkgs_w_different_key_id(system_info.key_ids_rhel, "kernel")
        non_rhel_kernels = [pkghandler.get_pkg_nevra(kernel) for kernel in non_rhel_kernels_pkg_info]

        # Get the latest installed rhel kernel
        #already_installed = re.findall(r" (.*?)(?: is)? already installed", output, re.MULTILINE)
        rhel_kernels = pkghandler.get_installed_pkgs_by_key_id(system_info.key_ids_rhel, name="kernel")

        if not rhel_kernels:
            # install the rhel kernel if any unavailable
            pkghandler.handle_no_newer_rhel_kernel_available()
            # get installed rhel kernel again
            rhel_kernels = pkghandler.get_installed_pkgs_by_key_id(system_info.key_ids_rhel, name="kernel")
        elif not non_rhel_kernels:
            return

        latest_installed_rhel_kernel = pkghandler.get_highest_package_version(("RHEL kernel", rhel_kernels))
        is_target_higher_than_rhel = pkghandler.compare_package_versions(target_kernel, latest_installed_rhel_kernel)

        if is_target_higher_than_rhel == 0:
            # latest rhel kernel is already installed, any other action needed
            return

        latest_installed_non_rhel_kernel = pkghandler.get_highest_package_version(("NON-RHEL kernel", non_rhel_kernels))
        is_target_higher_than_nonrhel = pkghandler.compare_package_versions(target_kernel, latest_installed_non_rhel_kernel)


        if is_target_higher_than_nonrhel == 1:
            # target rhel kernel is higher then the original
            return
        elif is_target_higher_than_nonrhel == 0:
            # versions are the same
            # replace the rhel kernel
            pkghandler.handle_no_newer_rhel_kernel_available()
        elif is_target_higher_than_nonrhel == -1:
            # target kernel is older then the kernel from original vendor
            pkghandler.handle_no_newer_rhel_kernel_available()

        ## end of new code

        # Check which of the kernel versions are already installed.
        # Example output from yum and dnf:
        #  "Package kernel-4.18.0-193.el8.x86_64 is already installed."
        # When calling install, yum/dnf essentially reports all the already installed versions.
        already_installed = re.findall(r" (.*?)(?: is)? already installed", output, re.MULTILINE)

        # Mitigates an edge case, when the kernel meta-package might not be installed prior to the conversion
        # with only kernel-core being on the system.
        # During that scenario the kernel meta package gets actually installed leaving the already_installed unmatched
        if not already_installed:
            return

        # Get list of kernel pkgs not signed by Red Hat
        non_rhel_kernels_pkg_info = pkghandler.get_installed_pkgs_w_different_key_id(system_info.key_ids_rhel, "kernel")
        # Extract the NEVRA from the package object to a list
        non_rhel_kernels = [pkghandler.get_pkg_nevra(kernel) for kernel in non_rhel_kernels_pkg_info]
        rhel_kernels = [kernel for kernel in already_installed if kernel not in non_rhel_kernels]

        # There is no RHEL kernel installed on the system at this point.
        # Generally that would mean, that there is either only one kernel
        # package installed on the system by the time of the conversion.
        # Or none of the kernel packages installed is possible to be handled
        # during the main transaction.
        if not rhel_kernels:
            info_message = (
                "Conflict of kernels: The running kernel has the same version as the latest RHEL kernel.\n"
                "The kernel package could not be replaced during the main transaction.\n"
                "We will try to install a lower version of the package,\n"
                "remove the conflicting kernel and then update to the latest security patched version."
            )
            loggerinst.info("\n{}".format(info_message))
            pkghandler.handle_no_newer_rhel_kernel_available()
            _kernel_update_needed = True

        # In this case all kernel packages were already replaced during the main transaction.
        # Having elif here to prevent breaking the action. Otherwise, when the first condition applies,
        # and the pkghandler.handle_no_newer_rhel_kernel_available() we can assume the Action finished.
        elif not non_rhel_kernels:
            return

        # At this point we need to decide if the highest package version in the rhel_kernels list
        # is higher than the highest package version in the non_rhel_kernels list
        else:
            latest_installed_non_rhel_kernel = pkghandler.get_highest_package_version(
                ("non-RHEL kernel", non_rhel_kernels)
            )
            loggerinst.debug(
                "Latest installed kernel version from the original vendor: {}".format(latest_installed_non_rhel_kernel)
            )
            latest_installed_rhel_kernel = pkghandler.get_highest_package_version(("RHEL kernel", rhel_kernels))
            loggerinst.debug("Latest installed RHEL kernel version: {}".format(latest_installed_rhel_kernel))
            is_rhel_kernel_higher = pkghandler.compare_package_versions(
                latest_installed_rhel_kernel, latest_installed_non_rhel_kernel
            )

            # If the highest version of the RHEL kernel package installed at this point is indeed
            # higher than any non-RHEL package, we don't need to do anything else.
            if is_rhel_kernel_higher == 1:
                return

            # This also contains a scenario, where the running non-RHEL kernel is of a higher version
            # than the latest one available in the RHEL repositories.
            # That might happen and happened before, when the original vendor patches the package
            # with a higher release number.
            pkghandler.handle_no_newer_rhel_kernel_available()
            _kernel_update_needed = True
        """


class VerifyRhelKernelInstalled(actions.Action):
    id = "VERIFY_RHEL_KERNEL_INSTALLED"
    dependencies = ("INSTALL_RHEL_KERNEL",)

    def run(self):
        """Verify that the RHEL kernel has been successfully installed and raise an ERROR if not"""
        super(VerifyRhelKernelInstalled, self).run()

        loggerinst.info("Verifying that RHEL kernel has been installed")
        installed_rhel_kernels = pkghandler.get_installed_pkgs_by_key_id(system_info.key_ids_rhel, name="kernel")
        if len(installed_rhel_kernels) <= 0:
            self.set_result(
                level="ERROR",
                id="NO_RHEL_KERNEL_INSTALLED",
                title="No RHEL kernel installed",
                description="There is no RHEL kernel installed on the system.",
                remediations="Verify that the repository used for installing kernel contains RHEL packages.",
            )
            return

        loggerinst.info("RHEL kernel has been verified to be on the system.")
        self.add_message(
            level="INFO",
            id="RHEL_KERNEL_INSTALL_VERIFIED",
            title="RHEL kernel install verified",
            description="The RHEL kernel has been verified to be on the system.",
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
                loggerinst.debug("Removing boot entry {}".format(entry))
                os.remove(entry)

        # Removing a boot entry that used to be the default makes grubby to choose a different entry as default,
        # but we will call grub --set-default to set the new default on all the proper places, e.g. for grub2-editenv
        output, ret_code = utils.run_subprocess(["/usr/sbin/grubby", "--default-kernel"], print_output=False)
        if ret_code:
            # Not setting the default entry shouldn't be a deal breaker and the reason to stop the conversions,
            # grub should pick one entry in any case.
            description = "Couldn't get the default GRUB2 boot loader entry:\n{}".format(output)
            loggerinst.warning(description)
            self.add_message(
                level="WARNING",
                id="UNABLE_TO_GET_GRUB2_BOOT_LOADER_ENTRY",
                title="Unable to get the GRUB2 boot loader entry",
                description=description,
            )
            return
        loggerinst.debug("Setting RHEL kernel {} as the default boot loader entry.".format(output.strip()))
        output, ret_code = utils.run_subprocess(["/usr/sbin/grubby", "--set-default", output.strip()])
        if ret_code:
            description = "Couldn't set the default GRUB2 boot loader entry:\n{}".format(output)
            loggerinst.warning(description)
            self.add_message(
                level="WARNING",
                id="UNABLE_TO_SET_GRUB2_BOOT_LOADER_ENTRY",
                title="Unable to set the GRUB2 boot loader entry",
                description=description,
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

        loggerinst.info("Checking for incorrect boot kernel")
        kernel_sys_cfg = utils.get_file_content("/etc/sysconfig/kernel")

        possible_kernels = ["kernel-uek", "kernel-plus"]
        kernel_to_change = next(
            iter(kernel for kernel in possible_kernels if kernel in kernel_sys_cfg),
            None,
        )
        if kernel_to_change:
            description = "Detected leftover boot kernel, changing to RHEL kernel"
            loggerinst.warning(description)
            self.add_message(
                level="WARNING",
                id="LEFTOVER_BOOT_KERNEL_DETECTED",
                title="Leftover boot kernel detected",
                description=description,
            )
            # need to change to "kernel" in rhel7 and "kernel-core" in rhel8
            new_kernel_str = "DEFAULTKERNEL=" + ("kernel" if system_info.version.major == 7 else "kernel-core")

            kernel_sys_cfg = kernel_sys_cfg.replace("DEFAULTKERNEL=" + kernel_to_change, new_kernel_str)
            utils.store_content_to_file("/etc/sysconfig/kernel", kernel_sys_cfg)
            loggerinst.info("Boot kernel {} was changed to {}".format(kernel_to_change, new_kernel_str))
        else:
            loggerinst.debug("Boot kernel validated.")


class KernelPkgsInstall(actions.Action):
    id = "KERNEL_PACKAGES_INSTALLATION"
    dependencies = ("VERIFY_RHEL_KERNEL_INSTALLED",)

    def run(self):
        """Install kernel packages and remove non-RHEL kernels."""
        super(KernelPkgsInstall, self).run()

        kernel_pkgs_to_install = self.remove_non_rhel_kernels()
        if kernel_pkgs_to_install:
            self.install_additional_rhel_kernel_pkgs(kernel_pkgs_to_install)

    def remove_non_rhel_kernels(self):
        loggerinst.info("Searching for non-RHEL kernels ...")
        non_rhel_kernels = pkghandler.get_installed_pkgs_w_different_key_id(system_info.key_ids_rhel, "kernel*")
        if not non_rhel_kernels:
            loggerinst.info("None found.")
            return None

        loggerinst.info("Removing non-RHEL kernels\n")
        pkghandler.print_pkg_info(non_rhel_kernels)
        pkgs_to_remove = [pkghandler.get_pkg_nvra(pkg) for pkg in non_rhel_kernels]
        utils.remove_pkgs(pkgs_to_remove)
        return non_rhel_kernels

    def install_additional_rhel_kernel_pkgs(self, additional_pkgs):
        """Convert2rhel removes all non-RHEL kernel packages, including kernel-tools, kernel-headers, etc. This function
        tries to install back all of these from RHEL repositories.
        """
        # OL renames some of the kernel packages by adding "-uek" (Unbreakable
        # Enterprise Kernel), e.g. kernel-uek-devel instead of kernel-devel. Such
        # package names need to be mapped to the RHEL kernel package names to have
        # them installed on the converted system.
        ol_kernel_ext = "-uek"
        pkg_names = [p.nevra.name.replace(ol_kernel_ext, "", 1) for p in additional_pkgs]
        for name in set(pkg_names):
            if name != "kernel":
                loggerinst.info("Installing RHEL {}".format(name))
                pkgmanager.call_yum_cmd("install", args=[name])


class UpdateKernel(actions.Action):
    id = "UPDATE_KERNEL"
    dependencies = ("FIX_DEFAULT_KERNEL",)

    def run(self):
        super(UpdateKernel, self).run()
        # Solution for RHELC-1707
        # This variable is set in the InstallRhelKernel action
        global _kernel_update_needed

        pkghandler.update_rhel_kernel()
        """
        cmd = ["repoquery", "kernel", "--envra"]
        # extract the nvra from the envra, format epoch:name-version-release.architecture
        target_kernel, _ = utils.run_subprocess(cmd)

        target_kernel = target_kernel.split(":")[1]

        rhel_kernels = pkghandler.get_installed_pkgs_by_key_id(system_info.key_ids_rhel, name="kernel")

        loggerinst.debug("RHEL Kernels: {}".format(rhel_kernels))

        latest_installed_rhel_kernel = pkghandler.get_highest_package_version(("RHEL kernel", rhel_kernels))

        loggerinst.debug("Latest RHEL Kernel: {}".format(latest_installed_rhel_kernel))
        is_target_higher_than_rhel = pkghandler.compare_package_versions(target_kernel, latest_installed_rhel_kernel)

        if is_target_higher_than_rhel == 1:
            pkghandler.update_rhel_kernel()
        else:
            loggerinst.info("RHEL kernel already present in latest version. Update not needed.\n")
        """
