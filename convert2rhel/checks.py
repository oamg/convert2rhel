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


import itertools
import logging
import os
import re

from convert2rhel import grub
from convert2rhel.pkghandler import call_yum_cmd, get_installed_pkg_objects, get_pkg_fingerprint
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import get_file_content, run_subprocess


logger = logging.getLogger(__name__)

KERNEL_REPO_RE = re.compile(r"^.+:(?P<version>.+).el.+$")
KERNEL_REPO_VER_SPLIT_RE = re.compile(r"\W+")
BAD_KERNEL_RELEASE_SUBSTRINGS = ("uek", "rt", "linode")

LINK_KMODS_RH_POLICY = "https://access.redhat.com/third-party-software-support"
# The kernel version stays the same throughout a RHEL major version
COMPATIBLE_KERNELS_VERS = {
    6: "2.6.32",
    7: "3.10.0",
    8: "4.18.0",
}


def perform_pre_checks():
    """Early checks after system facts should be added here."""
    check_efi()
    check_tainted_kmods()
    check_readonly_mounts()
    check_rhel_compatible_kernel_is_used()
    check_custom_repos_are_valid()


def perform_pre_ponr_checks():
    """Late checks before ponr should be added here."""
    ensure_compatibility_of_kmods()


def check_efi():
    """Inhibit the conversion when we are not able to handle UEFI."""
    logger.task("Prepare: Checking the firmware interface type (BIOS/UEFI)")
    if not grub.is_efi():
        logger.info("BIOS detected.")
        return
    logger.info("UEFI detected.")
    if system_info.version.major == 6:
        logger.critical("The conversion with UEFI is possible only for systems of major version 7 and newer.")
    if not os.path.exists("/usr/sbin/efibootmgr"):
        logger.critical("Install efibootmgr to continue converting the UEFI-based system.")
    if system_info.arch != "x86_64":
        logger.critical("Only x86_64 systems are supported for UEFI conversions.")
    if grub.is_secure_boot():
        logger.info("Secure boot detected.")
        logger.critical(
            "The conversion with secure boot is currently not possible.\n"
            "To disable it, follow the instructions available in this article: https://access.redhat.com/solutions/6753681"
        )

    # Get information about the bootloader. Currently the data is not used, but it's
    # good to check that we can obtain all the required data before the PONR. Better to
    # stop now than after the PONR.
    try:
        efiboot_info = grub.EFIBootInfo()
    except grub.BootloaderError as e:
        logger.critical(e.message)

    if not efiboot_info.entries[efiboot_info.current_bootnum].is_referring_to_file():
        # NOTE(pstodulk): I am not sure what could be consequences after the conversion, as the
        # new UEFI bootloader entry is created referring to a RHEL UEFI binary.
        logger.warning(
            "The current UEFI bootloader '%s' is not referring to any binary UEFI"
            " file located on local EFI System Partition (ESP)." % efiboot_info.current_bootnum
        )
    # TODO(pstodulk): print warning when multiple orig. UEFI entries point
    # to the original system (e.g. into the centos/ directory..). The point is
    # that only the current UEFI bootloader entry is handled.
    # If e.g. on CentOS Linux, other entries with CentOS labels could be
    # invalid (or at least misleading) as the OS will be replaced by RHEL


def check_tainted_kmods():
    """Stop the conversion when a loaded tainted kernel module is detected.

    Tainted kmods ends with (...) in /proc/modules, for example:
        multipath 20480 0 - Live 0x0000000000000000
        linear 20480 0 - Live 0x0000000000000000
        system76_io 16384 0 - Live 0x0000000000000000 (OE)  <<<<<< Tainted
        system76_acpi 16384 0 - Live 0x0000000000000000 (OE) <<<<< Tainted
    """
    unsigned_modules, _ = run_subprocess(["grep", "(", "/proc/modules"])
    module_names = "\n  ".join([mod.split(" ")[0] for mod in unsigned_modules.splitlines()])
    if unsigned_modules:
        logger.critical(
            "Tainted kernel module(s) detected. "
            "Third-party components are not supported per our "
            "software support policy\n{0}\n\n"
            "Uninstall or disable the following module(s) and run convert2rhel "
            "again to continue with the conversion:\n  {1}".format(LINK_KMODS_RH_POLICY, module_names)
        )


def check_readonly_mounts():
    """
    Mounting directly to /mnt/ is not in line with Unix FS (https://en.wikipedia.org/wiki/Unix_filesystem).
    Having /mnt/ and /sys/ read-only causes the installation of the filesystem package to
    fail (https://bugzilla.redhat.com/show_bug.cgi?id=1887513, https://github.com/oamg/convert2rhel/issues/123).
    """
    logger.task("Prepare: Checking /mnt and /sys are read-write")

    mounts = get_file_content("/proc/mounts", as_list=True)
    for line in mounts:
        _, mount_point, _, flags, _, _ = line.split()
        flags = flags.split(",")
        if mount_point not in ("/mnt", "/sys"):
            continue
        if "ro" in flags:
            if mount_point == "/mnt":
                logger.critical(
                    "Stopping conversion due to read-only mount to /mnt directory.\n"
                    "Mount at a subdirectory of /mnt to have /mnt writeable."
                )
            else:  # /sys
                logger.critical(
                    "Stopping conversion due to read-only mount to /sys directory.\n"
                    "Ensure mount point is writable before executing convert2rhel."
                )
        logger.debug("%s mount point is not read-only." % mount_point)
    logger.info("Read-only /mnt or /sys mount points not detected.")


def check_custom_repos_are_valid():
    """To prevent failures past the PONR, make sure that the enabled custom repositories are valid.

    What is meant by valid:
    - YUM/DNF is able to find the repoids (to rule out a typo)
    - the repository "baseurl" is accessible and contains repository metadata
    """
    logger.task("Prepare: Checking if --enablerepo repositories are accessible")

    if not tool_opts.no_rhsm:
        logger.info("Skipping the check of repositories due to the use of RHSM for the conversion.")
        return

    # Without clearing the metadata cache, the `yum makecache` command may return 0 (everything's ok) even when
    # the baseurl of a repository is not accessible. That would happen when the repository baseurl is changed but yum
    # still uses the previous baseurl stored in its cache.
    call_yum_cmd(command="clean", args=["metadata"], print_output=False)

    output, ret_code = call_yum_cmd(
        command="makecache", args=["-v", "--setopt=*.skip_if_unavailable=False"], print_output=False
    )
    if ret_code != 0:
        logger.critical(
            "Unable to access the repositories passed through the --enablerepo option. "
            "For more details, see YUM/DNF output:\n{0}".format(output)
        )
    else:
        logger.debug("Output of the previous yum command:\n{0}".format(output))

    logger.info("The repositories passed through the --enablerepo option are all accessible.")


def ensure_compatibility_of_kmods():
    """Ensure if the host kernel modules are compatible with RHEL."""
    host_kmods = get_loaded_kmods()
    rhel_supported_kmods = get_rhel_supported_kmods()
    unsupported_kmods = get_unsupported_kmods(host_kmods, rhel_supported_kmods)
    if unsupported_kmods:
        not_supported_kmods = "\n".join(
            map(
                lambda kmod: "/lib/modules/{kver}/{kmod}".format(kver=system_info.booted_kernel, kmod=kmod),
                unsupported_kmods,
            )
        )
        logger.critical(
            (
                "The following kernel modules are not supported in RHEL:\n{kmods}\n"
                "Make sure you have updated the kernel to the latest available version and rebooted the system. "
                "Remove the unsupported modules and run convert2rhel again to continue with the conversion."
            ).format(kmods=not_supported_kmods, system=system_info.name)
        )
    else:
        logger.debug("Kernel modules are compatible.")


def get_loaded_kmods():
    """Get a set of kernel modules loaded on host.

    Each module we cut part of the path until the kernel release
    (i.e. /lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz ->
    kernel/lib/a.ko.xz) in order to be able to compare with RHEL
    kernel modules in case of different kernel release
    """
    logger.debug("Getting a list of loaded kernel modules.")
    lsmod_output, _ = run_subprocess(["lsmod"], print_output=False)
    modules = re.findall(r"^(\w+)\s.+$", lsmod_output, flags=re.MULTILINE)[1:]
    return set(
        _get_kmod_comparison_key(run_subprocess(["modinfo", "-F", "filename", module], print_output=False)[0])
        for module in modules
    )


def _get_kmod_comparison_key(path):
    """Create a comparison key from the kernel module abs path.

    Converts /lib/modules/5.8.0-7642-generic/kernel/lib/a.ko.xz ->
    kernel/lib/a.ko.xz

    Why:
        The standard kernel modules are located under
        /lib/modules/{some kernel release}/.
        If we want to make sure that the kernel package is present
        on RHEL, we need to compare the full path, but because kernel release
        might be different, we compare the relative paths after kernel release.
    """
    return "/".join(path.strip().split("/")[4:])


def get_rhel_supported_kmods():
    """Return set of target RHEL supported kernel modules."""
    basecmd = [
        "repoquery",
        "--releasever=%s" % system_info.releasever,
    ]
    if system_info.version.major == 8:
        basecmd.append("--setopt=module_platform_id=platform:el8")

    for repoid in system_info.get_enabled_rhel_repos():
        basecmd.extend(("--repoid", repoid))

    cmd = basecmd[:]
    cmd.append("-f")
    cmd.append("/lib/modules/*.ko*")
    # Without the release package installed, dnf can't determine the modularity
    #   platform ID.
    # get output of a command to get all packages which are the source
    # of kmods
    kmod_pkgs_str, _ = run_subprocess(cmd, print_output=False)

    # from these packages we select only the latest one
    kmod_pkgs = get_most_recent_unique_kernel_pkgs(kmod_pkgs_str.rstrip("\n").split())
    if not kmod_pkgs:
        logger.debug("Output of the previous repoquery command:\n{0}".format(kmod_pkgs_str))
        logger.critical(
            "No packages containing kernel modules available in the enabled repositories ({0}).".format(
                ", ".join(system_info.get_enabled_rhel_repos())
            )
        )
    else:
        logger.info(
            "Comparing the loaded kernel modules with the modules available in the following RHEL"
            " kernel packages available in the enabled repositories:\n {0}".format("\n ".join(kmod_pkgs))
        )

    # querying obtained packages for files they produces
    cmd = basecmd[:]
    cmd.append("-l")
    cmd.extend(kmod_pkgs)
    rhel_kmods_str, _ = run_subprocess(cmd, print_output=False)

    return get_rhel_kmods_keys(rhel_kmods_str)


def get_most_recent_unique_kernel_pkgs(pkgs):
    """Return the most recent versions of all kernel packages.

    When we scan kernel modules provided by kernel packages
    it is expensive to check each kernel pkg. Since each new
    kernel pkg do not deprecate kernel modules we only select
    the most recent ones.

    All RHEL kmods packages starts with kernel* or kmod*

    For example, we have the following packages list:
        kernel-core-0:4.18.0-240.10.1.el8_3.x86_64
        kernel-core-0:4.19.0-240.10.1.el8_3.x86_64
        kmod-debug-core-0:4.18.0-240.10.1.el8_3.x86_64
        kmod-debug-core-0:4.18.0-245.10.1.el8_3.x86_64
    ==> (output of this function will be)
        kernel-core-0:4.19.0-240.10.1.el8_3.x86_64
        kmod-debug-core-0:4.18.0-245.10.1.el8_3.x86_64

    _repos_version_key extract the version of a package
        into the tuple, i.e.
        kernel-core-0:4.18.0-240.10.1.el8_3.x86_64 ==>
        (4, 15, 0, 240, 10, 1)


    :type pkgs: Iterable[str]
    :type pkgs_groups:
        Iterator[
            Tuple[
                package_name_without_version,
                Iterator[package_name, ...],
                ...,
            ]
        ]
    """

    pkgs_groups = itertools.groupby(sorted(pkgs), lambda pkg_name: pkg_name.split(":")[0])
    return tuple(
        max(distinct_kernel_pkgs[1], key=_repos_version_key)
        for distinct_kernel_pkgs in pkgs_groups
        if distinct_kernel_pkgs[0].startswith(("kernel", "kmod"))
    )


def _repos_version_key(pkg_name):
    try:
        rpm_version = KERNEL_REPO_RE.search(pkg_name).group("version")
    except AttributeError:
        logger.critical(
            "Unexpected package:\n%s\n is a source of kernel modules.",
            pkg_name,
        )
    else:
        return tuple(
            map(
                _convert_to_int_or_zero,
                KERNEL_REPO_VER_SPLIT_RE.split(rpm_version),
            )
        )


def _convert_to_int_or_zero(s):
    try:
        return int(s)
    except ValueError:
        return 0


def get_rhel_kmods_keys(rhel_kmods_str):
    return set(
        _get_kmod_comparison_key(kmod_path)
        for kmod_path in filter(
            lambda path: path.endswith(("ko.xz", "ko")),
            rhel_kmods_str.rstrip("\n").split(),
        )
    )


def get_unsupported_kmods(host_kmods, rhel_supported_kmods):
    """Return a set of those installed kernel modules that are not available in RHEL repositories.

    Ignore certain kmods mentioned in the system configs. These kernel modules moved to kernel core, meaning that the
    functionality is retained and we would be incorrectly saying that the modules are not supported in RHEL."""
    return host_kmods - rhel_supported_kmods - set(system_info.kmods_to_ignore)


def check_rhel_compatible_kernel_is_used():
    """Ensure the booted kernel is signed, is standard (not UEK, realtime, ...), and has the same version as in RHEL.

    By requesting that, we can be confident that the RHEL kernel will provide the same capabilities as on the
    original system.
    """
    logger.task("Prepare: Check kernel compatibility with RHEL")
    if any(
        (
            _bad_kernel_version(system_info.booted_kernel),
            _bad_kernel_package_signature(system_info.booted_kernel),
            _bad_kernel_substring(system_info.booted_kernel),
        )
    ):
        logger.critical(
            "The booted kernel version is incompatible with the standard RHEL kernel. "
            "To proceed with the conversion, boot into a kernel that is available in the {0} {1} base repository"
            " by executing the following steps:\n\n"
            "1. Ensure that the {0} {1} base repository is enabled\n"
            "2. Run: yum install kernel\n"
            "3. (optional) Run: grubby --set-default "
            '/boot/vmlinuz-`rpm -q --qf "%{{BUILDTIME}}\\t%{{EVR}}.%{{ARCH}}\\n" kernel | sort -nr | head -1 | cut -f2`\n'
            "4. Reboot the machine and if step 3 was not applied choose the kernel"
            " installed in step 2 manually".format(system_info.name, system_info.version.major)
        )
    else:
        logger.info("Kernel is compatible with RHEL")


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
    kernel_pkg = run_subprocess(
        ["rpm", "-qf", "--qf", "%{NAME}", "/boot/vmlinuz-%s" % kernel_release], print_output=False
    )[0]
    logger.debug("Booted kernel package name: {0}".format(kernel_pkg))
    kernel_pkg_obj = get_installed_pkg_objects(kernel_pkg)[0]
    kernel_pkg_gpg_fingerprint = get_pkg_fingerprint(kernel_pkg_obj)
    bad_signature = system_info.cfg_content["gpg_fingerprints"] != kernel_pkg_gpg_fingerprint
    # e.g. Oracle Linux Server -> Oracle
    os_vendor = system_info.name.split()[0]
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
