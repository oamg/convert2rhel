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

from itertools import imap
import re
import yum
import logging
import os

from convert2rhel.systeminfo import system_info
from convert2rhel import utils
from convert2rhel.toolopts import tool_opts

# Limit the number of loops over yum command calls for the case there was
# an error.
MAX_YUM_CMD_CALLS = 2


class PkgWFingerprint(object):
    """Tuple-like storage for the RPM object of a package and a fingerprint
    with which the package was signed.
    """
    def __init__(self, pkg_obj, fingerprint):
        self.pkg_obj = pkg_obj
        self.fingerprint = fingerprint


def call_yum_cmd_w_downgrades(cmd, fingerprints):
    """Calling yum command is prone to end up with an error due to unresolved
    dependencies, especially when it tries to downgrade pkgs. This function
    tries to resolve the dependency errors where yum is not able to.
    """

    loggerinst = logging.getLogger(__name__)
    for _ in xrange(MAX_YUM_CMD_CALLS):
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


def call_yum_cmd(command, args="", enablerepo=None, disablerepo=None,
                 print_output=True):
    """Call yum command and optionally print its output."""
    loggerinst = logging.getLogger(__name__)

    cmd = "yum %s -y" % (command)
    # disablerepo parameter must be added before the enablerepo parameter

    if disablerepo is None:
        disablerepo = []
    if disablerepo:
        repos = disablerepo
    else:
        repos = tool_opts.disablerepo
    for repo in repos:
        cmd += " --disablerepo=%s " % repo

    if enablerepo is None:
        enablerepo = []
    if enablerepo:
        repos = enablerepo
    else:
        repos = tool_opts.enablerepo
    for repo in repos:
        cmd += " --enablerepo=%s " % repo
    if args:
        cmd += " " + args

    stdout, returncode = utils.run_subprocess(cmd, print_output=print_output)
    # handle when yum returns non-zero code when there is nothing to do
    nothing_to_do_error_exists = stdout.endswith("Error: Nothing to do\n")
    if returncode == 1 and nothing_to_do_error_exists:
        loggerinst.info("Return code 1 however nothing to do. Returning code 0"
                        " ... ")
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

    # distro-sync is not available until yum v3.2.28:
    #  (http://yum.baseurl.org/wiki/whatsnew/3.2.28)
    # linux 5.x only provides yum v3.2.22 so we need to use downgrade argument
    #  instead of distro-sync
    cmd = "downgrade"
    if int(system_info.version) >= 6:
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
    """Return a list of objects, each holding one of the installed packages
    (rpm object) and GPG key fingerprints used to sign it. The packages can be
    optionally filtered by name.
    """
    package_objects = get_installed_pkg_objects(name)
    pkgs_w_fingerprints = []
    for pkg_obj in package_objects:
        pkg_sig = pkg_obj.hdr.sprintf("%|DSAHEADER?{%{DSAHEADER:pgpsig}}:"
                                      "{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:"
                                      "{(none)}|}|")
        fingerprint_match = re.search("Key ID (.*)", pkg_sig)
        if fingerprint_match:
            pkgs_w_fingerprints.append(PkgWFingerprint(
                pkg_obj, fingerprint_match.group(1)))
        else:
            pkgs_w_fingerprints.append(PkgWFingerprint(pkg_obj, "none"))
    return pkgs_w_fingerprints


def get_installed_pkg_objects(name=""):
    """Return list with installed package objects. The packages can be
    optionally filtered by name.
    """
    yum_base = yum.YumBase()
    # Disable plugins (when kept enabled yum outputs useless text every call)
    yum_base.doConfigSetup(init_plugins=False)
    if name:
        return yum_base.rpmdb.returnPackages(patterns=[name])
    else:
        return yum_base.rpmdb.returnPackages()


def get_third_party_pkgs():
    """Get all the third party packages (non-Red Hat and non-original OS
    signed) which are going to be kept untouched.
    """
    third_party_pkgs = get_installed_pkgs_w_different_fingerprint(
        system_info.fingerprints_orig_os + system_info.fingerprints_rhel)
    return third_party_pkgs


def get_installed_pkgs_w_different_fingerprint(fingerprints, name=""):
    """Return list of all the packages (rpm objects) that are not signed
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


def print_pkg_info(pkgs):
    """Print package information."""
    for pkg in pkgs:
        if not pkg.vendor:
            pkg.vendor = "N/A"
    max_nvra_length = max(imap(len, map(lambda pkg: get_pkg_nvra(pkg), pkgs)))
    max_vendor_length = max(max(imap(len, map(lambda pkg: pkg.vendor, pkgs))),
                            len("Vendor"))
    loggerinst = logging.getLogger(__name__)
    result = "%-*s  %-*s  %s" % (max_nvra_length, "Package", max_vendor_length,
                                 "Vendor", "Repository") + "\n"
    loggerinst.info("%-*s  %-*s  %s"
                    % (max_nvra_length, "Package", max_vendor_length, "Vendor",
                       "Repository"))
    result += "%-*s  %-*s  %s" % (max_nvra_length, "-" * len("Package"),
                                  max_vendor_length, "-" * len("Vendor"),
                                  "-" * len("Repository")) + "\n"
    loggerinst.info("%-*s  %-*s  %s"
                    % (max_nvra_length, "-" * len("Package"),
                       max_vendor_length, "-" * len("Vendor"),
                       "-" * len("Repository")))
    for pkg in pkgs:
        try:
            from_repo = pkg.yumdb_info.from_repo
        except (KeyError, AttributeError):
            # A package may not have repo set if it's installed by rpm.
            # KeyError is for Python 2.4, AttributeError is for Python 2.6+ due
            # to a different implementation of rpm library.
            from_repo = "N/A"
        result += "%-*s  %-*s  %s" % (max_nvra_length, get_pkg_nvra(pkg),
                                      max_vendor_length, pkg.vendor,
                                      from_repo) + "\n"
        loggerinst.info("%-*s  %-*s  %s"
                        % (max_nvra_length, get_pkg_nvra(pkg),
                           max_vendor_length, pkg.vendor,
                           from_repo))
    loggerinst.info("")
    return result


def get_pkg_nvra(pkg_obj):
    return "%s-%s-%s.%s" % (pkg_obj.name,
                            pkg_obj.version,
                            pkg_obj.release,
                            pkg_obj.arch)


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
    return


def remove_blacklisted_pkgs():
    """Certain packages need to be removed before the system conversion,
    depending on the system to be converted. At least removing <os>-release
    package is a must.
    """
    loggerinst = logging.getLogger(__name__)
    installed_blacklisted_pkgs = []
    loggerinst.info("Searching for the following blacklisted packages:\n")
    for blacklisted_pkg in system_info.pkg_blacklist:
        temp = '.' * (50 - len(blacklisted_pkg) - 2)
        pkg_objects = get_installed_pkg_objects(blacklisted_pkg)
        installed_blacklisted_pkgs.extend(pkg_objects)
        loggerinst.info("%s %s %s" %
                        (blacklisted_pkg, temp, str(len(pkg_objects))))

    if not installed_blacklisted_pkgs:
        loggerinst.info("\nNothing to do.")
        return
    loggerinst.info("\n")
    loggerinst.warning("The following packages will be removed...")
    loggerinst.info("\n")
    print_pkg_info(installed_blacklisted_pkgs)
    utils.ask_to_continue()
    utils.remove_pkgs([get_pkg_nvra(pkg)
                      for pkg in installed_blacklisted_pkgs])
    return


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

    # distro-sync/downgrade the packages that had the following:
    #  'Installed package <package> not available.'
    # distro-sync is not available until yum v3.2.28:
    #  (http://yum.baseurl.org/wiki/whatsnew/3.2.28)
    # linux 5.x only provides yum v3.2.22 so we need to use downgrade argument
    #  instead of distro-sync
    cmd = "downgrade"
    if int(system_info.version) >= 6:
        cmd = "distro-sync"
    loggerinst.info("Performing %s of the packages left ..." % cmd)
    call_yum_cmd_w_downgrades(cmd, system_info.fingerprints_orig_os)

    return


def preserve_only_rhel_kernel():
    loggerinst = logging.getLogger(__name__)
    needs_update = install_rhel_kernel()
    non_rhel_kernel_pkgs = remove_non_rhel_kernels()
    if non_rhel_kernel_pkgs:
        install_additional_rhel_kernel_pkgs(non_rhel_kernel_pkgs)
    if needs_update:
        loggerinst.info("Updating RHEL kernel.")
        call_yum_cmd(command="update", args="kernel")
    return


def install_rhel_kernel():
    """Return boolean indicating whether it's needed to update the kernel
    later on.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Installing RHEL kernel ...")
    output, ret_code = call_yum_cmd(command="install", args="kernel")

    # check condition - failed installation
    if ret_code:
        loggerinst.critical("Error occured while attempting to install the"
                            " RHEL kernel")

    # check condition - kernel with same version is already installed
    already_installed = re.search(r" (.*?) already installed", output)
    if already_installed:
        kernel_version = already_installed.group(1)
        kernel_obj = get_installed_pkgs_w_different_fingerprint(
            system_info.fingerprints_rhel, kernel_version)
        if kernel_obj:
            # If the installed kernel is from a third party (non-RHEL) and has
            # the same NEVRA as the one available from RHEL repos, it's
            # necessary to install an older version RHEL kernel, because the
            # third party one will be removed later in the conversion process.
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
            utils.remove_pkgs(["kernel-%s" % older])
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
        pkg=pkg, dest=utils.tmp_dir, disablerepo=tool_opts.disablerepo,
        enablerepo=tool_opts.enablerepo)
    if ret_code != 0:
        loggerinst.critical("Unable to download %s from RHEL repository" % pkg)
        return

    loggerinst.info("Replacing %s %s with RHEL kernel with the same NEVRA ... " % (system_info.name, pkg))
    output, ret_code = utils.run_subprocess(
        'rpm -i --force --replacepkgs %s*' % os.path.join(utils.tmp_dir, pkg),
        print_output=False)
    if ret_code != 0:
        loggerinst.critical("Unable to replace kernel package: %s" % output)
        return

    loggerinst.info("\nRHEL %s installed.\n" % pkg)


def remove_non_rhel_kernels():
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Searching for non-RHEL kernels ...")
    non_rhel_kernels = get_installed_pkgs_w_different_fingerprint(
        system_info.fingerprints_rhel, "kernel*")
    if non_rhel_kernels:
        loggerinst.info("Removing non-RHEL kernels")
        print_pkg_info(non_rhel_kernels)
        utils.remove_pkgs([get_pkg_nvra(pkg) for pkg in non_rhel_kernels])
    else:
        loggerinst.info("None found.")
    return non_rhel_kernels


def install_additional_rhel_kernel_pkgs(additional_pkgs):
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
    return
