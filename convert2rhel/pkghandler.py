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

import glob
import logging
import os
import re
import rpm

from convert2rhel.systeminfo import system_info
from convert2rhel import utils
from convert2rhel import pkgmanager
from convert2rhel.toolopts import tool_opts

# Limit the number of loops over yum command calls for the case there was
# an error.
MAX_YUM_CMD_CALLS = 2

_VERSIONLOCK_FILE_PATH = '/etc/yum/pluginconf.d/versionlock.list'  # This file is used by the dnf plugin as well
versionlock_file = utils.RestorableFile(_VERSIONLOCK_FILE_PATH)  # pylint: disable=C0103


class PkgWFingerprint(object):
    """Tuple-like storage for a package object and a fingerprint with which the package was signed."""

    def __init__(self, pkg_obj, fingerprint):
        self.pkg_obj = pkg_obj
        self.fingerprint = fingerprint


def call_yum_cmd_w_downgrades(cmd, fingerprints):
    """Calling yum command is prone to end up with an error due to unresolved
    dependencies, especially when it tries to downgrade pkgs. This function
    tries to resolve the dependency errors where yum is not able to.
    """

    loggerinst = logging.getLogger(__name__)
    for _ in range(MAX_YUM_CMD_CALLS):
        output, ret_code = call_yum_cmd(cmd, "%s" % (" ".join(
            get_installed_pkgs_by_fingerprint(fingerprints))))
        loggerinst.info("Received return code: %s\n" % str(ret_code))
        # handle success condition #1
        if ret_code == 0:
            break
        # handle success condition #2
        # false positive: yum returns non-zero code when there is nothing to do
        nothing_to_do_error_exists = output.endswith("Error: Nothing to do\n")
        if ret_code == 1 and nothing_to_do_error_exists:
            break
        # handle error condition
        loggerinst.info("Resolving dependency errors ... ")
        resolve_dep_errors(output, [])
    else:
        loggerinst.critical("Could not resolve yum errors.")
    return


def call_yum_cmd(command, args="", print_output=True):
    """Call yum command and optionally print its output."""
    loggerinst = logging.getLogger(__name__)

    cmd = "yum %s -y" % command

    # The --disablerepo yum option must be added before --enablerepo,
    #   otherwise the enabled repo gets disabled if --disablerepo="*" is used
    for repo in tool_opts.disablerepo:
        cmd += " --disablerepo=%s" % repo

    # When using subscription-manager for the conversion, use those repos for the yum call that have been enabled
    # through subscription-manager
    repos_to_enable = system_info.submgr_enabled_repos if not tool_opts.disable_submgr else tool_opts.enablerepo

    for repo in repos_to_enable:
        cmd += " --enablerepo=%s" % repo

    if args:
        cmd += " " + args

    stdout, returncode = utils.run_subprocess(cmd, print_output=print_output)
    # handle when yum returns non-zero code when there is nothing to do
    nothing_to_do_error_exists = stdout.endswith("Error: Nothing to do\n")
    if returncode == 1 and nothing_to_do_error_exists:
        loggerinst.debug("Yum has nothing to do. Ignoring.")
        returncode = 0
    return stdout, returncode


def get_problematic_pkgs(output, known_problematic_pkgs):
    new_problematic_pkgs = []
    package_nevr_re = "[0-9]*:?([a-z-][a-z0-9-]*?)-[0-9]"

    loggerinst = logging.getLogger(__name__)
    loggerinst.info("\n\n")
    protected = re.findall("Error.*?\"(.*?)\".*?protected",
                           output, re.MULTILINE)
    loggerinst.info("Found protected packages: %s" % protected)
    deps = re.findall("Error: Package: %s" % package_nevr_re,
                      output, re.MULTILINE)
    loggerinst.info("Found deps packages: %s" % deps)
    multilib = re.findall("multilib versions: %s" % package_nevr_re,
                          output, re.MULTILINE)
    loggerinst.info("Found multilib packages: %s" % multilib)
    req = re.findall("Requires: ([a-z-]*)", output, re.MULTILINE)
    loggerinst.info("Found req packages: %s" % req)

    if protected + deps + multilib + req:
        newpkg = list(set(protected + deps + multilib + req) -
                      set(known_problematic_pkgs))
        loggerinst.info("Adding packages to yum command: %s" % newpkg)
        new_problematic_pkgs.extend(list(set(protected + deps + multilib + req)
                                         - set(known_problematic_pkgs)))
    return known_problematic_pkgs + new_problematic_pkgs


def resolve_dep_errors(output, pkgs):
    """Recursive function. If there are dependency errors in the yum output,
    try to resolve them by yum downgrades.
    """
    loggerinst = logging.getLogger(__name__)

    prev_pkgs = pkgs
    pkgs = get_problematic_pkgs(output, pkgs)
    if set(prev_pkgs) == set(pkgs):
        # No package has been added to the list of packages to be downgraded.
        # There's no point in calling the yum downgrade command again.
        loggerinst.info("No other package to try to downgrade in order to"
                        " resolve yum dependency errors.")
        return

    cmd = "distro-sync"
    loggerinst.info("\n\nTrying to resolve the following packages: %s"
                    % ", ".join(pkgs))
    output, ret_code = call_yum_cmd(command=cmd, args=" %s" % " ".join(pkgs))
    if ret_code != 0:
        resolve_dep_errors(output, pkgs)
    return


def get_installed_pkgs_by_fingerprint(fingerprints, name=""):
    """Return list of those installed packages (just names) which are signed
    by the specific OS GPG keys. Fingerprints of the GPG keys are passed as a
    list in the fingerprints parameter. The packages can be optionally
    filtered by name.
    """
    pkgs_w_fingerprints = get_installed_pkgs_w_fingerprints(name)
    return [pkg.pkg_obj.name for pkg in pkgs_w_fingerprints
            if pkg.fingerprint in fingerprints]


def get_installed_pkgs_w_fingerprints(name=""):
    """Return a list of objects, each holding one of the installed packages (yum.rpmsack.RPMInstalledPackage in case
    of yum and hawkey.Package in case of dnf) and GPG key fingerprints used to sign it. The packages can be
    optionally filtered by name.
    """
    package_objects = get_installed_pkg_objects(name)
    pkgs_w_fingerprints = []
    for pkg_obj in package_objects:
        fingerprint = get_pkg_fingerprint(pkg_obj)
        pkgs_w_fingerprints.append(PkgWFingerprint(pkg_obj, fingerprint))

    return pkgs_w_fingerprints


def get_pkg_fingerprint(pkg_obj):
    """Get fingerprint of the key used to sign a package"""
    loggerinst = logging.getLogger(__name__)
    if pkgmanager.TYPE == 'yum':
        hdr = pkg_obj.hdr
    elif pkgmanager.TYPE == 'dnf':
        hdr = get_rpm_header(pkg_obj)

    pkg_sig = hdr.sprintf(
        '%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{(none)}|}|')
    fingerprint_match = re.search("Key ID (.*)", pkg_sig)
    if fingerprint_match:
        return fingerprint_match.group(1)
    else:
        return "none"


def get_rpm_header(pkg_obj):
    """The dnf python API does not provide the package rpm header:
      https://bugzilla.redhat.com/show_bug.cgi?id=1876606.
    So instead, we're getting the header directly from the rpm db.
    """
    ts = rpm.TransactionSet()
    rpm_hdr_iter = ts.dbMatch('name', pkg_obj.name)
    for rpm_hdr in rpm_hdr_iter:
        # There might be multiple pkgs with the same name installed.
        if rpm_hdr[rpm.RPMTAG_VERSION] == pkg_obj.v and rpm_hdr[rpm.RPMTAG_RELEASE] == pkg_obj.r:
            # One might think that we could have used the package EVR for comparison, instead of version and release
            #  separately, but there's a bug: https://bugzilla.redhat.com/show_bug.cgi?id=1876885.
            return rpm_hdr
    else:
        # Package not found in the rpm db
        loggerinst = logging.getLogger(__name__)
        loggerinst.critical(
            "Unable to find package '%s' in the rpm database." % pkg_obj.name)


def get_installed_pkg_objects(name=""):
    """Return list with installed package objects. The packages can be
    optionally filtered by name.
    """
    if pkgmanager.TYPE == 'yum':
        return _get_installed_pkg_objects_yum(name)
    elif pkgmanager.TYPE == 'dnf':
        return _get_installed_pkg_objects_dnf(name)


def _get_installed_pkg_objects_yum(name):
    yum_base = pkgmanager.YumBase()
    # Disable plugins (when kept enabled yum outputs useless text every call)
    yum_base.doConfigSetup(init_plugins=False)
    if name:
        return yum_base.rpmdb.returnPackages(patterns=[name])
    return yum_base.rpmdb.returnPackages()


def _get_installed_pkg_objects_dnf(name):
    dnf_base = pkgmanager.Base()
    dnf_base.fill_sack(load_system_repo=True, load_available_repos=False)
    query = dnf_base.sack.query()
    installed = query.installed()
    if name:
        # name__glob provides "shell-style wildcard match" per
        #  https://dnf.readthedocs.io/en/latest/api_queries.html#dnf.query.Query.filter
        installed = installed.filter(name__glob=name)
    return list(installed)


def get_third_party_pkgs():
    """Get all the third party packages (non-Red Hat and non-original OS
    signed) which are going to be kept untouched.
    """
    third_party_pkgs = get_installed_pkgs_w_different_fingerprint(
        system_info.fingerprints_orig_os + system_info.fingerprints_rhel)
    return third_party_pkgs


def get_installed_pkgs_w_different_fingerprint(fingerprints, name=""):
    """Return list of all the packages (yum.rpmsack.RPMInstalledPackage objects in case
    of yum and hawkey.Package objects in case of dnf) that are not signed
    by the specific OS GPG keys. Fingerprints of the GPG keys are passed as a
    list in the fingerprints parameter. The packages can be optionally
    filtered by name.
    """
    if not fingerprints:
        # if fingerprints is None skip this check.
        return []
    pkgs_w_fingerprints = get_installed_pkgs_w_fingerprints(name)
    # Skip the gpg-pubkey package, it never has a signature
    return [pkg.pkg_obj for pkg in pkgs_w_fingerprints
            if pkg.fingerprint not in fingerprints and
            pkg.pkg_obj.name != "gpg-pubkey"]


def list_third_party_pkgs():
    """List packages not packaged by the original OS vendor or Red Hat and warn that these are not going
    to be converted.
    """
    loggerinst = logging.getLogger(__name__)
    third_party_pkgs = get_third_party_pkgs()
    if third_party_pkgs:
        loggerinst.warning("Only packages signed by %s are to be"
                           " reinstalled. Red Hat support won't be provided"
                           " for the following third party packages:\n"
                           % system_info.name)
        print_pkg_info(third_party_pkgs)
        utils.ask_to_continue()
    else:
        loggerinst.info("No third party packages installed.")


def print_pkg_info(pkgs):
    """Print package information.
    We print a packager instead of a vendor because the dnf python API does not provide the information about vendor
    (https://bugzilla.redhat.com/show_bug.cgi?id=1876561).
    """
    max_nvra_length = max(map(len, [get_pkg_nvra(pkg) for pkg in pkgs]))
    max_packager_length = max(max(map(len, [get_packager(pkg) for pkg in pkgs])), len("Packager"))

    header = "%-*s  %-*s  %s" % (max_nvra_length, "Package", max_packager_length,
                                 "Packager", "Repository") + "\n"
    header_underline = "%-*s  %-*s  %s" % (max_nvra_length, "-" * len("Package"),
                                           max_packager_length, "-" * len("Packager"),
                                           "-" * len("Repository")) + "\n"

    pkg_list = ""
    for pkg in pkgs:
        if pkgmanager.TYPE == 'yum':
            try:
                from_repo = pkg.yumdb_info.from_repo
            except AttributeError:
                # A package may not have the installation repo set in case it was installed through rpm
                from_repo = "N/A"

        elif pkgmanager.TYPE == 'dnf':
            # There's no public attribute for getting the installation repository.
            # Bug filed: https://bugzilla.redhat.com/show_bug.cgi?id=1879168
            from_repo = pkg._from_repo

        pkg_list += "%-*s  %-*s  %s" % (max_nvra_length, get_pkg_nvra(pkg),
                                        max_packager_length, get_packager(pkg), from_repo) + "\n"

    pkg_table = header + header_underline + pkg_list
    loggerinst = logging.getLogger(__name__)
    loggerinst.info(pkg_table)
    return pkg_table


def get_pkg_nvra(pkg_obj):
    """Get package NVRA as a string: name, version, release, architecture.

    Some utilities don't accept the full NEVRA of a package, for example rpm.
    """
    return "%s-%s-%s.%s" % (pkg_obj.name,
                            pkg_obj.version,
                            pkg_obj.release,
                            pkg_obj.arch)


def get_pkg_nevra(pkg_obj):
    """Get package NEVRA as a string: name, epoch, version, release, architecture.

    Epoch is included only when non-zero. However it's on a different position when printed by YUM or DNF:
      YUM - epoch before name: "7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      DNF - epoch before version: "oraclelinux-release-8:8.2-1.0.8.el8.x86_64"
    """
    if pkgmanager.TYPE == 'yum':
        return "%s%s-%s-%s.%s" % ("" if str(pkg_obj.epoch) == "0" else str(pkg_obj.epoch) + ":",
                                  pkg_obj.name,
                                  pkg_obj.version,
                                  pkg_obj.release,
                                  pkg_obj.arch)
    elif pkgmanager.TYPE == 'dnf':
        return "%s-%s%s-%s.%s" % (pkg_obj.name,
                                  "" if str(pkg_obj.epoch) == "0" else str(pkg_obj.epoch) + ":",
                                  pkg_obj.version,
                                  pkg_obj.release,
                                  pkg_obj.arch)


def get_packager(pkg_obj):
    # The packager may not be set for all packages
    packager = pkg_obj.packager if pkg_obj.packager else "N/A"
    # Typical packager format:
    #  Red Hat, Inc. <http://bugzilla.redhat.com/bugzilla>
    #  CentOS Buildsys <bugs@centos.org>
    # Get only the string before the left angle bracket
    return packager.split("<", 1)[0].rstrip()


def list_non_red_hat_pkgs_left():
    """List all the packages that have not been replaced by the
    Red Hat-signed ones during the conversion.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Listing packages not signed by Red Hat")
    non_red_hat_pkgs = get_installed_pkgs_w_different_fingerprint(
        system_info.fingerprints_rhel)
    if non_red_hat_pkgs:
        loggerinst.info("The following packages were left unchanged.")
        print_pkg_info(non_red_hat_pkgs)
    else:
        loggerinst.info("All packages are now signed by Red Hat.")


def remove_excluded_pkgs():
    """Certain packages need to be removed before the system conversion,
    depending on the system to be converted. At least removing <os>-release
    package is a must.
    """
    loggerinst = logging.getLogger(__name__)
    installed_excluded_pkgs = []
    loggerinst.info("Searching for the following excluded packages:\n")
    for excluded_pkg in system_info.excluded_pkgs:
        temp = '.' * (50 - len(excluded_pkg) - 2)
        pkg_objects = get_installed_pkg_objects(excluded_pkg)
        installed_excluded_pkgs.extend(pkg_objects)
        loggerinst.info("%s %s %s" %
                        (excluded_pkg, temp, str(len(pkg_objects))))

    if not installed_excluded_pkgs:
        loggerinst.info("\nNothing to do.")
        return
    loggerinst.info("\n")
    loggerinst.warning("The following packages will be removed...")
    print_pkg_info(installed_excluded_pkgs)
    utils.ask_to_continue()
    utils.remove_pkgs([get_pkg_nvra(pkg) for pkg in installed_excluded_pkgs])
    loggerinst.debug("Successfully removed %s packages" % str(len(installed_excluded_pkgs)))


def replace_non_red_hat_packages():
    """Wrapper for yum commands that replace the non-Red Hat packages with
    the Red Hat ones.
    """
    loggerinst = logging.getLogger(__name__)

    # TODO: run yum commands with --assumeno first and show the user what will
    # be done and then ask if we should continue the operation

    loggerinst.info(
        "Performing update of the %s packages ..." % system_info.name)
    call_yum_cmd_w_downgrades("update", system_info.fingerprints_orig_os)

    loggerinst.info(
        "Performing reinstallation of the %s packages ..." % system_info.name)
    call_yum_cmd_w_downgrades("reinstall", system_info.fingerprints_orig_os)

    # distro-sync (downgrade) the packages that had the following:
    #  'Installed package <package> not available.'
    cmd = "distro-sync"
    loggerinst.info("Performing %s of the packages left ..." % cmd)
    call_yum_cmd_w_downgrades(cmd, system_info.fingerprints_orig_os)


def install_gpg_keys():
    loggerinst = logging.getLogger(__name__)
    gpg_path = os.path.join(utils.DATA_DIR, "gpg-keys")
    gpg_keys = [os.path.join(gpg_path, key) for key in os.listdir(gpg_path)]
    for gpg_key in gpg_keys:
        output, ret_code = utils.run_subprocess(
            'rpm --import %s' % os.path.join(gpg_path, gpg_key),
            print_output=False)
        if ret_code != 0:
            loggerinst.critical("Unable to import GPG key: %s", output)


def preserve_only_rhel_kernel():
    kernel_update_needed = install_rhel_kernel()
    verify_rhel_kernel_installed()

    kernel_pkgs_to_install = remove_non_rhel_kernels()
    fix_invalid_grub2_entries()

    if kernel_pkgs_to_install:
        install_additional_rhel_kernel_pkgs(kernel_pkgs_to_install)
    if kernel_update_needed:
        update_rhel_kernel()


def install_rhel_kernel():
    """Return boolean indicating whether it's needed to update the kernel
    later on.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Installing RHEL kernel ...")
    output, ret_code = call_yum_cmd(command="install", args="kernel")

    if ret_code != 0:
        loggerinst.critical("Error occured while attempting to install the"
                            " RHEL kernel")

    # Check if kernel with same version is already installed.
    # Example output from yum and dnf:
    #  "Package kernel-2.6.32-754.33.1.el6.x86_64 already installed and latest version"
    #  "Package kernel-4.18.0-193.el8.x86_64 is already installed."
    already_installed = re.search(r" (.*?)(?: is)? already installed", output, re.MULTILINE)
    if already_installed:
        rhel_kernel_nevra = already_installed.group(1)
        non_rhel_kernels = get_installed_pkgs_w_different_fingerprint(system_info.fingerprints_rhel, "kernel")
        for non_rhel_kernel in non_rhel_kernels:
            # We're comparing to NEVRA since that's what yum/dnf prints out
            if rhel_kernel_nevra == get_pkg_nevra(non_rhel_kernel):
                # If the installed kernel is from a third party (non-RHEL) and has the same NEVRA as the one available
                # from RHEL repos, it's necessary to install an older version RHEL kernel and the third party one will
                # be removed later in the conversion process. It's because yum/dnf is unable to reinstall a kernel.
                loggerinst.info("\nConflict of kernels: One of the installed kernels"
                                " has the same version as the latest RHEL kernel.")
                handle_no_newer_rhel_kernel_available()
                return True
    return False


def handle_no_newer_rhel_kernel_available():
    """Handle cases when the installed third party (non-RHEL) kernel has the
    same version as (or newer than) the RHEL one available in the RHEL repo(s).
    """
    installed, available = get_kernel_availability()
    to_install = [kernel for kernel in available if kernel not in installed]

    if not to_install:
        # All the available RHEL kernel versions are already installed
        if len(installed) > 1:
            # There's more than one installed non-RHEL kernel. We'll remove one
            # of them - the one that has the same version as the available RHEL
            # kernel
            older = available[-1]
            utils.remove_pkgs(pkgs_to_remove=["kernel-%s" % older], should_backup=False)
            call_yum_cmd(command="install", args="kernel-%s" % older)
        else:
            replace_non_rhel_installed_kernel(installed[0])

        return

    # Install the latest out of the available non-clashing RHEL kernels
    call_yum_cmd(command="install", args="kernel-%s" % to_install[-1])


def get_kernel_availability():
    """Return a tuple - a list of installed kernel versions and a list of
    available kernel versions.
    """
    output, _ = call_yum_cmd(command="list", args="--showduplicates kernel",
                             print_output=False)
    return (list(get_kernel(data))
            for data in output.split("Available Packages"))


def get_kernel(kernels_raw):
    for kernel in re.findall(
            r"kernel.*?\s+(\S+)\s+\S+",
            kernels_raw, re.MULTILINE):
        yield kernel


def replace_non_rhel_installed_kernel(version):
    """Replace the installed non-RHEL kernel with RHEL kernel with same
    version.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.warning("The convert2rhel is going to force-replace the only"
                       " kernel installed, which has the same NEVRA as the"
                       " only available RHEL kernel. If anything goes wrong"
                       " with such replacement, the system will become"
                       " unbootable. If you want the convert2rhel to install"
                       " the RHEL kernel in a safer manner, you can install a"
                       " different version of kernel first and then run"
                       " convert2rhel again.")
    utils.ask_to_continue()

    pkg = "kernel-%s" % version

    ret_code = utils.download_pkg(
        pkg=pkg, dest=utils.TMP_DIR, disablerepo=tool_opts.disablerepo,
        enablerepo=tool_opts.enablerepo)
    if ret_code != 0:
        return

    loggerinst.info("Replacing %s %s with RHEL kernel with the same NEVRA ... " % (system_info.name, pkg))
    output, ret_code = utils.run_subprocess(
        'rpm -i --force --replacepkgs %s*' % os.path.join(utils.TMP_DIR, pkg),
        print_output=False)
    if ret_code != 0:
        loggerinst.critical("Unable to replace kernel package: %s" % output)
        return

    loggerinst.info("\nRHEL %s installed.\n" % pkg)


def verify_rhel_kernel_installed():
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Verifying that RHEL kernel has been installed")
    if not is_rhel_kernel_installed():
        loggerinst.critical(
            "No RHEL kernel installed. Verify that the repository used for installing kernel contains RHEL packages.")
    else:
        loggerinst.info("RHEL kernel has been installed.")


def is_rhel_kernel_installed():
    installed_rhel_kernels = get_installed_pkgs_by_fingerprint(system_info.fingerprints_rhel, name="kernel")
    return len(installed_rhel_kernels) > 0


def remove_non_rhel_kernels():
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Searching for non-RHEL kernels ...")
    non_rhel_kernels = get_installed_pkgs_w_different_fingerprint(
        system_info.fingerprints_rhel, "kernel*")
    if non_rhel_kernels:
        loggerinst.info("Removing non-RHEL kernels")
        print_pkg_info(non_rhel_kernels)
        utils.remove_pkgs(pkgs_to_remove=[get_pkg_nvra(pkg) for pkg in non_rhel_kernels], should_backup=False)
    else:
        loggerinst.info("None found.")
    return non_rhel_kernels


def fix_invalid_grub2_entries():
    """
    On systems derived from RHEL 8 and later, /etc/machine-id is being used to identify grub2 boot loader entries per
    the Boot Loader Specification.

    However, at the time of executing convert2rhel, the current machine-id can be different from the machine-id from the
    time when the kernels were installed. If that happens:
    - convert2rhel installs the RHEL kernel, but it's not set as default
    - convert2rhel removes the original OS kernels, but for these the boot entries are not removed

    The solution handled by this function is to remove the non-functioning boot entries upon the removal of the original
    OS kernels, and setting the RHEL kernel as default.
    """
    if int(system_info.version) < 8 or system_info.arch == "s390x":
        # Applicable only on systems derived from RHEL 8 and later, and systems using GRUB2 (s390x uses zipl)
        return

    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Fixing GRUB boot loader entries.")

    machine_id = utils.get_file_content("/etc/machine-id")
    boot_entries = glob.glob("/boot/loader/entries/*.conf")
    for entry in boot_entries:
        # The boot loader entries in /boot/loader/entries/<machine-id>-<kernel-version>.conf
        if machine_id.strip() not in os.path.basename(entry):
            loggerinst.debug("Removing boot entry %s" % entry)
            os.remove(entry)

    # Removing a boot entry that used to be the default makes grubby to choose a different entry as default, but we will
    # call grub --set-default to set the new default on all the proper places, e.g. for grub2-editenv
    output, ret_code = utils.run_subprocess("/usr/sbin/grubby --default-kernel", print_output=False)
    if ret_code:
        # Not setting the default entry shouldn't be a deal breaker and the reason to stop the conversions, grub should
        # pick one entry in any case.
        loggerinst.warning("Couldn't get the default GRUB2 boot loader entry:\n%s" % output)
        return
    loggerinst.debug("Setting RHEL kernel %s as the default boot loader entry." % output.strip())
    output, ret_code = utils.run_subprocess("/usr/sbin/grubby --set-default %s" % output.strip())
    if ret_code:
        loggerinst.warning("Couldn't set the default GRUB2 boot loader entry:\n%s" % output)


def install_additional_rhel_kernel_pkgs(additional_pkgs):
    """Convert2rhel removes all non-RHEL kernel packages, including kernel-tools, kernel-headers, etc. This function
    tries to install back all of these from RHEL repositories.
    """
    loggerinst = logging.getLogger(__name__)
    # OL renames some of the kernel packages by adding "-uek" (Unbreakable
    # Enterprise Kernel), e.g. kernel-uek-devel instead of kernel-devel. Such
    # package names need to be mapped to the RHEL kernel package names to have
    # them installed on the converted system.
    ol_kernel_ext = '-uek'
    pkg_names = [p.name.replace(ol_kernel_ext, '', 1) for p in additional_pkgs]
    for name in set(pkg_names):
        if name != "kernel":
            loggerinst.info("Installing RHEL %s" % name)
            call_yum_cmd("install %s" % name)


def update_rhel_kernel():
    """In the corner case where the original system kernel version is the same as the latest available RHEL kernel,
    convert2rhel needs to install older RHEL kernel version first. In this function, RHEL kernel is updated to the
    latest available version.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Updating RHEL kernel.")
    call_yum_cmd(command="update", args="kernel")


def clear_versionlock():
    """A package can be locked to a specific version using a YUM/DNF versionlock plugin. Then, even if a newer version
    of a package is available, yum or dnf won't update it. That may cause a problem during the conversion as other
    RHEL packages may depend on a different version than is locked. That's why we clear all the locks to prevent a
    system conversion failure.
    DNF has been designed to be backwards compatible with YUM. So the file in which the version locks are defined for
    YUM works correctly even with DNF thanks to symlinks created by DNF.
    """
    loggerinst = logging.getLogger(__name__)

    if os.path.isfile(_VERSIONLOCK_FILE_PATH) and os.path.getsize(_VERSIONLOCK_FILE_PATH) > 0:
        loggerinst.warn("YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        loggerinst.info("Upon continuing, we will clear all package version locks.")
        utils.ask_to_continue()

        versionlock_file.backup()

        loggerinst.info("Clearing package versions locks...")
        call_yum_cmd("versionlock clear", print_output=False)
    else:
        loggerinst.info("Usage of YUM/DNF versionlock plugin not detected.")
