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

from convert2rhel import pkgmanager, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


loggerinst = logging.getLogger(__name__)

# Limit the number of loops over yum command calls for the case there was
# an error.
MAX_YUM_CMD_CALLS = 3

_VERSIONLOCK_FILE_PATH = "/etc/yum/pluginconf.d/versionlock.list"  # This file is used by the dnf plugin as well
versionlock_file = utils.RestorableFile(_VERSIONLOCK_FILE_PATH)  # pylint: disable=C0103


class PkgWFingerprint(object):
    """Tuple-like storage for a package object and a fingerprint with which the package was signed."""

    def __init__(self, pkg_obj, fingerprint):
        self.pkg_obj = pkg_obj
        self.fingerprint = fingerprint


def call_yum_cmd_w_downgrades(cmd, pkgs, retries=MAX_YUM_CMD_CALLS):
    """Calling yum command is prone to end up with an error due to unresolved
    dependencies, especially when it tries to downgrade pkgs. This function
    tries to resolve the dependency errors where yum is not able to.
    """

    if retries <= 0:
        loggerinst.critical("Could not resolve yum errors.")

    output, ret_code = call_yum_cmd(cmd, "%s" % (" ".join(pkgs)))
    loggerinst.info("Received return code: %s\n" % str(ret_code))
    # handle success condition #1
    if ret_code == 0:
        return

    # handle success condition #2
    # false positive: yum returns non-zero code when there is nothing to do
    nothing_to_do_error_exists = output.endswith("Error: Nothing to do\n")
    if ret_code == 1 and nothing_to_do_error_exists:
        return

    # handle error condition
    loggerinst.info("Resolving dependency errors ... ")
    output = resolve_dep_errors(output)

    # if we have problematic packages, remove them
    problematic_pkgs = get_problematic_pkgs(output)
    to_remove = problematic_pkgs["errors"] | problematic_pkgs["mismatches"]
    if to_remove:
        loggerinst.warning("Removing problematic packages to continue with conversion:\n%s" % "\n".join(to_remove))
        utils.remove_pkgs(to_remove, backup=False, critical=False)
    return call_yum_cmd_w_downgrades(cmd, pkgs, retries - 1)


def call_yum_cmd(
    command,
    args="",
    print_output=True,
    enable_repos=None,
    disable_repos=None,
    set_releasever=True,
):
    """Call yum command and optionally print its output.

    The enable_repos and disable_repos function parameters accept lists and they override the default use of repos,
    which is:
    * --disablerepo yum option = "*" by default OR passed through a CLI option by the user
    * --enablerepo yum option = is the repo enabled through subscription-manager based on a convert2rhel configuration
      file for the particular system OR passed through a CLI option by the user

    YUM/DNF typically expands the $releasever variable used in repofiles. However it fails to do so after we remove the
    release packages (centos-release, oraclelinux-release, etc.) and before the redhat-release package is installed.
    By default, for the above reason, we provide the --releasever option to each yum call. However before we remove the
    release package, we need YUM/DNF to expand the variable by itself (for that, use set_releasever=False).
    """

    cmd = "yum %s -y" % command

    # The --disablerepo yum option must be added before --enablerepo,
    #   otherwise the enabled repo gets disabled if --disablerepo="*" is used
    repos_to_disable = []
    if isinstance(disable_repos, list):
        repos_to_disable = disable_repos
    else:
        repos_to_disable = tool_opts.disablerepo

    for repo in repos_to_disable:
        cmd += " --disablerepo=%s" % repo

    if set_releasever and system_info.releasever:
        cmd += " --releasever=%s" % system_info.releasever

    # Without the release package installed, dnf can't determine the modularity platform ID.
    if system_info.version.major == 8:
        cmd += " --setopt=module_platform_id=platform:el8"

    repos_to_enable = []
    if isinstance(enable_repos, list):
        repos_to_enable = enable_repos
    else:
        # When using subscription-manager for the conversion, use those repos for the yum call that have been enabled
        # through subscription-manager
        repos_to_enable = system_info.get_enabled_rhel_repos()

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


def get_problematic_pkgs(output, excluded_pkgs=frozenset()):
    """Parse the YUM/DNF output to find what packages are causing a transaction failure."""
    loggerinst.info("Checking for problematic packages")
    problematic_pkgs = {
        "protected": set(),
        "errors": set(),
        "multilib": set(),
        "required": set(),
        "mismatches": set(),
    }
    loggerinst.info("\n\n")

    protected = re.findall('Error.*?"(.*?)".*?protected', output, re.MULTILINE)
    if protected:
        loggerinst.info("Found protected packages: %s" % set(protected))
        problematic_pkgs["protected"] = set(protected) - excluded_pkgs

    package_nevr_re = r"[0-9]*:?([a-z][a-z0-9-_]*?)-[0-9]"
    deps = re.findall("Error: Package: %s" % package_nevr_re, output, re.MULTILINE)
    if deps:
        loggerinst.info("Found packages causing dependency errors: %s" % set(deps))
        problematic_pkgs["errors"] = set(deps) - excluded_pkgs

    multilib = re.findall("multilib versions: %s" % package_nevr_re, output, re.MULTILINE)
    if multilib:
        loggerinst.info("Found multilib packages: %s" % set(multilib))
        problematic_pkgs["multilib"] = set(multilib) - excluded_pkgs

    mismatches = re.findall("problem with installed package %s" % package_nevr_re, output, re.MULTILINE)
    if mismatches:
        loggerinst.info("Found mismatched packages: %s" % set(mismatches))
        problematic_pkgs["mismatches"] = set(mismatches) - excluded_pkgs

    # What yum prints in the Requires is a capability, not a package name. And capability can be an arbitrary string,
    # e.g. perl(Carp) or redhat-lsb-core(x86-64).
    # Yet, passing a capability to yum distro-sync does not yield the expected result - the packages that provide the
    # capability are not getting downgraded. So here we're getting only the part of a capability that consists of
    # package name characters only. It will work in most cases but not in all (e.g. "perl(Carp)").
    package_name_re = r"([a-z][a-z0-9-]*)"
    req = re.findall("Requires: %s" % package_name_re, output, re.MULTILINE)
    if req:
        loggerinst.info("Unavailable packages required by others: %s" % set(req))
        problematic_pkgs["required"] = set(req) - excluded_pkgs

    return problematic_pkgs


def get_pkgs_to_distro_sync(problematic_pkgs):
    """Consolidate all the different problematic packages to one list."""
    return (
        problematic_pkgs["errors"]
        | problematic_pkgs["protected"]
        | problematic_pkgs["multilib"]
        | problematic_pkgs["required"]
    )


def resolve_dep_errors(output, pkgs=frozenset()):
    """Recursive function. If there are dependency errors in the yum output,
    try to resolve them by yum downgrades.
    """

    problematic_pkgs = get_problematic_pkgs(output, excluded_pkgs=pkgs)
    pkgs_to_distro_sync = get_pkgs_to_distro_sync(problematic_pkgs)
    if not pkgs_to_distro_sync:
        # No package has been added to the list of packages to be downgraded.
        # There's no point in calling the yum downgrade command again.
        loggerinst.info("No other package to try to downgrade in order to resolve yum dependency errors.")
        return output
    pkgs_to_distro_sync = pkgs_to_distro_sync.union(pkgs)
    cmd = "distro-sync"
    loggerinst.info("\n\nTrying to resolve the following packages: %s" % ", ".join(pkgs_to_distro_sync))
    output, ret_code = call_yum_cmd(command=cmd, args=" %s" % " ".join(pkgs_to_distro_sync))
    if ret_code != 0:
        return resolve_dep_errors(output, pkgs_to_distro_sync)
    return output


def get_installed_pkgs_by_fingerprint(fingerprints, name=""):
    """Return list of those installed packages (just names) which are signed
    by the specific OS GPG keys. Fingerprints of the GPG keys are passed as a
    list in the fingerprints parameter. The packages can be optionally
    filtered by name.
    """
    pkgs_w_fingerprints = get_installed_pkgs_w_fingerprints(name)
    return [pkg.pkg_obj.name for pkg in pkgs_w_fingerprints if pkg.fingerprint in fingerprints]


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
    """Get fingerprint of the key used to sign a package."""
    pkg_sig = get_pkg_signature(pkg_obj)
    fingerprint_match = re.search("Key ID (.*)", pkg_sig)
    if fingerprint_match:
        return fingerprint_match.group(1)
    else:
        return "none"


def get_pkg_signature(pkg_obj):
    """Get information about a package signature from the RPM database."""
    if pkgmanager.TYPE == "yum":
        hdr = pkg_obj.hdr
    elif pkgmanager.TYPE == "dnf":
        hdr = get_rpm_header(pkg_obj)

    pkg_sig = hdr.sprintf("%|DSAHEADER?{%{DSAHEADER:pgpsig}}:{%|RSAHEADER?{%{RSAHEADER:pgpsig}}:{(none)}|}|")
    return pkg_sig


def get_rpm_header(pkg_obj):
    """The dnf python API does not provide the package rpm header:
      https://bugzilla.redhat.com/show_bug.cgi?id=1876606.
    So instead, we're getting the header directly from the rpm db.
    """
    ts = rpm.TransactionSet()
    rpm_hdr_iter = ts.dbMatch("name", pkg_obj.name)
    for rpm_hdr in rpm_hdr_iter:
        # There might be multiple pkgs with the same name installed.
        if rpm_hdr[rpm.RPMTAG_VERSION] == pkg_obj.v and rpm_hdr[rpm.RPMTAG_RELEASE] == pkg_obj.r:
            # One might think that we could have used the package EVR for comparison, instead of version and release
            #  separately, but there's a bug: https://bugzilla.redhat.com/show_bug.cgi?id=1876885.
            return rpm_hdr
    else:
        # Package not found in the rpm db
        loggerinst.critical("Unable to find package '%s' in the rpm database." % pkg_obj.name)


def get_installed_pkg_objects(name=""):
    """Return list with installed package objects. The packages can be
    optionally filtered by name.
    """
    if pkgmanager.TYPE == "yum":
        return _get_installed_pkg_objects_yum(name)
    elif pkgmanager.TYPE == "dnf":
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
    conf = dnf_base.conf
    conf.module_platform_id = "platform:el8"
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
        system_info.fingerprints_orig_os + system_info.fingerprints_rhel
    )
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
    return [
        pkg.pkg_obj
        for pkg in pkgs_w_fingerprints
        if pkg.fingerprint not in fingerprints and pkg.pkg_obj.name != "gpg-pubkey"
    ]


def list_third_party_pkgs():
    """List packages not packaged by the original OS vendor or Red Hat and warn that these are not going
    to be converted.
    """
    third_party_pkgs = get_third_party_pkgs()
    if third_party_pkgs:
        loggerinst.warning(
            "Only packages signed by %s are to be"
            " reinstalled. Red Hat support won't be provided"
            " for the following third party packages:\n" % system_info.name
        )
        print_pkg_info(third_party_pkgs)
        utils.ask_to_continue()
    else:
        loggerinst.info("No third party packages installed.")


def print_pkg_info(pkgs):
    """Print package information."""
    max_nvra_length = max(map(len, [get_pkg_nvra(pkg) for pkg in pkgs]))
    max_packager_length = max(
        max(
            map(
                len,
                [get_vendor(pkg) if hasattr(pkg, "vendor") else get_packager(pkg) for pkg in pkgs],
            )
        ),
        len("Vendor/Packager"),
    )

    header = (
        "%-*s  %-*s  %s"
        % (
            max_nvra_length,
            "Package",
            max_packager_length,
            "Vendor/Packager",
            "Repository",
        )
        + "\n"
    )
    header_underline = (
        "%-*s  %-*s  %s"
        % (
            max_nvra_length,
            "-" * len("Package"),
            max_packager_length,
            "-" * len("Vendor/Packager"),
            "-" * len("Repository"),
        )
        + "\n"
    )

    pkg_list = ""
    for pkg in pkgs:
        if pkgmanager.TYPE == "yum":
            try:
                from_repo = pkg.yumdb_info.from_repo
            except AttributeError:
                # A package may not have the installation repo set in case it was installed through rpm
                from_repo = "N/A"

        elif pkgmanager.TYPE == "dnf":
            # There's no public attribute for getting the installation repository.
            # Bug filed: https://bugzilla.redhat.com/show_bug.cgi?id=1879168
            from_repo = pkg._from_repo

        pkg_list += (
            "%-*s  %-*s  %s"
            % (
                max_nvra_length,
                get_pkg_nvra(pkg),
                max_packager_length,
                get_vendor(pkg) if hasattr(pkg, "vendor") else get_packager(pkg),
                from_repo,
            )
            + "\n"
        )

    pkg_table = header + header_underline + pkg_list
    loggerinst.info(pkg_table)
    return pkg_table


def get_pkg_nvra(pkg_obj):
    """Get package NVRA as a string: name, version, release, architecture.

    Some utilities don't accept the full NEVRA of a package, for example rpm.
    """
    return "%s-%s-%s.%s" % (
        pkg_obj.name,
        pkg_obj.version,
        pkg_obj.release,
        pkg_obj.arch,
    )


def get_pkg_nevra(pkg_obj):
    """Get package NEVRA as a string: name, epoch, version, release, architecture.

    Epoch is included only when non-zero. However it's on a different position when printed by YUM or DNF:
      YUM - epoch before name: "7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      DNF - epoch before version: "oraclelinux-release-8:8.2-1.0.8.el8.x86_64"
    """
    if pkgmanager.TYPE == "yum":
        return "%s%s-%s-%s.%s" % (
            "" if str(pkg_obj.epoch) == "0" else str(pkg_obj.epoch) + ":",
            pkg_obj.name,
            pkg_obj.version,
            pkg_obj.release,
            pkg_obj.arch,
        )
    elif pkgmanager.TYPE == "dnf":
        return "%s-%s%s-%s.%s" % (
            pkg_obj.name,
            "" if str(pkg_obj.epoch) == "0" else str(pkg_obj.epoch) + ":",
            pkg_obj.version,
            pkg_obj.release,
            pkg_obj.arch,
        )


def get_packager(pkg_obj):
    """Get the package packager from the yum/dnf package object.

    The packager may not be set for all packages. E.g. Oracle Linux packages have the packager info empty.
    """
    packager = pkg_obj.packager if pkg_obj.packager else "N/A"
    # Typical packager format:
    #  Red Hat, Inc. <http://bugzilla.redhat.com/bugzilla>
    #  CentOS Buildsys <bugs@centos.org>
    # Get only the string before the left angle bracket
    return packager.split("<", 1)[0].rstrip()


def get_vendor(pkg_obj):
    """Get the package vendor from the yum/dnf package object.

    The vendor information is provided by the yum/dnf python API on all systems except systems derived from
    RHEL 8.0-8.3 (see bug https://bugzilla.redhat.com/show_bug.cgi?id=1876561).
    """
    if hasattr(pkg_obj, "vendor") and pkg_obj.vendor:
        return pkg_obj.vendor
    else:
        return "N/A"


def list_non_red_hat_pkgs_left():
    """List all the packages that have not been replaced by the
    Red Hat-signed ones during the conversion.
    """
    loggerinst.info("Listing packages not signed by Red Hat")
    non_red_hat_pkgs = get_installed_pkgs_w_different_fingerprint(system_info.fingerprints_rhel)
    if non_red_hat_pkgs:
        loggerinst.info("The following packages were left unchanged.")
        print_pkg_info(non_red_hat_pkgs)
    else:
        loggerinst.info("All packages are now signed by Red Hat.")


def remove_excluded_pkgs():
    """Certain packages need to be removed before the system conversion,
    depending on the system to be converted.
    """
    loggerinst.info("Searching for the following excluded packages:\n")
    remove_pkgs_with_confirm(system_info.excluded_pkgs)


def remove_repofile_pkgs():
    """Remove those non-RHEL packages that contain YUM/DNF repofiles (/etc/yum.repos.d/*.repo) or affect variables
    in the repofiles (e.g. $releasever)

    We can't be removing them together with the other excluded packages - it wouldn't
    be possible to access and install subscription-manager dependencies. At the same time
    we can't install subscription-manager before removing the excluded packages
    as there would be a conflict with one of the excluded packages (rhn-client-tools).
    """
    loggerinst.info("Searching for packages containing repofiles or affecting variables in the repofiles:\n")
    remove_pkgs_with_confirm(system_info.repofile_pkgs)


def remove_pkgs_with_confirm(pkgs, backup=True):
    """
    Remove selected packages with a breakdown and user confirmation prompt.
    """
    pkgs_to_remove = []
    for pkg in pkgs:
        temp = "." * (50 - len(pkg) - 2)
        pkg_objects = get_installed_pkgs_w_different_fingerprint(system_info.fingerprints_rhel, pkg)
        pkgs_to_remove.extend(pkg_objects)
        loggerinst.info("%s %s %s" % (pkg, temp, str(len(pkg_objects))))

    if not pkgs_to_remove:
        loggerinst.info("\nNothing to do.")
        return
    loggerinst.info("\n")
    loggerinst.warning("The following packages will be removed...")
    print_pkg_info(pkgs_to_remove)
    utils.ask_to_continue()
    utils.remove_pkgs([get_pkg_nvra(pkg) for pkg in pkgs_to_remove], backup=backup)
    loggerinst.debug("Successfully removed %s packages" % str(len(pkgs_to_remove)))


def replace_non_red_hat_packages():
    """Wrapper for yum commands that replace the non-Red Hat packages with
    the Red Hat ones.
    """

    # The subscription-manager packages on Oracle Linux 6 are installed from CentOS Linux 6 repositories. They are
    # not replaced during the system conversion with the RHEL ones because convert2rhel replaces only packages
    # signed by the original system vendor (Oracle).

    submgr_pkgs = []
    if system_info.id == "oracle" and system_info.version.major == 6:
        submgr_pkgs += ["subscription-manager*"]

    # TODO: run yum commands with --assumeno first and show the user what will
    # be done and then ask if we should continue the operation

    loggerinst.info("Performing update of the %s packages ..." % system_info.name)
    orig_os_pkgs = get_installed_pkgs_by_fingerprint(system_info.fingerprints_orig_os)
    call_yum_cmd_w_downgrades("update", orig_os_pkgs + submgr_pkgs)

    loggerinst.info("Performing reinstallation of the %s packages ..." % system_info.name)
    orig_os_pkgs = get_installed_pkgs_by_fingerprint(system_info.fingerprints_orig_os)
    call_yum_cmd_w_downgrades("reinstall", orig_os_pkgs + submgr_pkgs)

    # distro-sync (downgrade) the packages that had the following:
    #  'Installed package <package> not available.'
    cmd = "distro-sync"
    loggerinst.info("Performing %s of the packages left ..." % cmd)
    orig_os_pkgs = get_installed_pkgs_by_fingerprint(system_info.fingerprints_orig_os)
    call_yum_cmd_w_downgrades(cmd, orig_os_pkgs + submgr_pkgs)


def install_gpg_keys():
    gpg_path = os.path.join(utils.DATA_DIR, "gpg-keys")
    gpg_keys = [os.path.join(gpg_path, key) for key in os.listdir(gpg_path)]
    for gpg_key in gpg_keys:
        output, ret_code = utils.run_subprocess(
            "rpm --import %s" % os.path.join(gpg_path, gpg_key),
            print_output=False,
        )
        if ret_code != 0:
            loggerinst.critical("Unable to import GPG key: %s", output)
        loggerinst.info("GPG keys imported.")


def preserve_only_rhel_kernel():
    kernel_update_needed = install_rhel_kernel()
    verify_rhel_kernel_installed()

    kernel_pkgs_to_install = remove_non_rhel_kernels()
    fix_invalid_grub2_entries()
    fix_default_kernel()

    if kernel_pkgs_to_install:
        install_additional_rhel_kernel_pkgs(kernel_pkgs_to_install)
    if kernel_update_needed:
        update_rhel_kernel()


def install_rhel_kernel():
    """Return boolean indicating whether it's needed to update the kernel
    later on.
    """
    loggerinst.info("Installing RHEL kernel ...")
    output, ret_code = call_yum_cmd(command="install", args="kernel")

    if ret_code != 0:
        loggerinst.critical("Error occured while attempting to install the RHEL kernel")

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
                loggerinst.info(
                    "\nConflict of kernels: One of the installed kernels"
                    " has the same version as the latest RHEL kernel."
                )
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
            utils.remove_pkgs(pkgs_to_remove=["kernel-%s" % older], backup=False)
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
    output, _ = call_yum_cmd(command="list", args="--showduplicates kernel", print_output=False)
    return (list(get_kernel(data)) for data in output.split("Available Packages"))


def get_kernel(kernels_raw):
    for kernel in re.findall(r"kernel.*?\s+(\S+)\s+\S+", kernels_raw, re.MULTILINE):
        yield kernel


def replace_non_rhel_installed_kernel(version):
    """Replace the installed non-RHEL kernel with RHEL kernel with same version."""
    loggerinst.warning(
        "The convert2rhel is going to force-replace the only"
        " kernel installed, which has the same NEVRA as the"
        " only available RHEL kernel. If anything goes wrong"
        " with such replacement, the system will become"
        " unbootable. If you want the convert2rhel to install"
        " the RHEL kernel in a safer manner, you can install a"
        " different version of kernel first and then run"
        " convert2rhel again."
    )
    utils.ask_to_continue()

    pkg = "kernel-%s" % version

    # For downloading the RHEL kernel we need to use the RHEL repositories.
    repos_to_enable = system_info.get_enabled_rhel_repos()
    path = utils.download_pkg(
        pkg=pkg,
        dest=utils.TMP_DIR,
        disable_repos=tool_opts.disablerepo,
        enable_repos=repos_to_enable,
    )
    if not path:
        loggerinst.critical("Unable to download the RHEL kernel package.")

    loggerinst.info("Replacing %s %s with RHEL kernel with the same NEVRA ... " % (system_info.name, pkg))
    output, ret_code = utils.run_subprocess(
        # The --nodeps is needed as some kernels depend on system-release (alias for redhat-release) and that package
        # is not installed at this stage.
        "rpm -i --force --nodeps --replacepkgs %s*" % os.path.join(utils.TMP_DIR, pkg),
        print_output=False,
    )
    if ret_code != 0:
        loggerinst.critical("Unable to replace the kernel package: %s" % output)

    loggerinst.info("\nRHEL %s installed.\n" % pkg)


def verify_rhel_kernel_installed():
    loggerinst.info("Verifying that RHEL kernel has been installed")
    if not is_rhel_kernel_installed():
        loggerinst.critical(
            "No RHEL kernel installed. Verify that the repository used for installing kernel contains RHEL packages."
        )
    else:
        loggerinst.info("RHEL kernel has been installed.")


def is_rhel_kernel_installed():
    installed_rhel_kernels = get_installed_pkgs_by_fingerprint(system_info.fingerprints_rhel, name="kernel")
    return len(installed_rhel_kernels) > 0


def remove_non_rhel_kernels():
    loggerinst.info("Searching for non-RHEL kernels ...")
    non_rhel_kernels = get_installed_pkgs_w_different_fingerprint(system_info.fingerprints_rhel, "kernel*")
    if non_rhel_kernels:
        loggerinst.info("Removing non-RHEL kernels")
        print_pkg_info(non_rhel_kernels)
        utils.remove_pkgs(
            pkgs_to_remove=[get_pkg_nvra(pkg) for pkg in non_rhel_kernels],
            backup=False,
        )
    else:
        loggerinst.info("None found.")
    return non_rhel_kernels


def fix_default_kernel():
    """
    Systems converted from Oracle Linux or CentOS Linux may have leftover kernel-uek or kernel-plus in
    /etc/sysconfig/kernel as DEFAULTKERNEL.
    This function fixes that by replacing the DEFAULTKERNEL setting from kernel-uek or kernel-plus to kernel for RHEL 6,7 and kernel-core for RHEL 8
    """
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
        # need to change to "kernel" in rhel6, 7 and "kernel-core" in rhel8
        new_kernel_str = "DEFAULTKERNEL=" + ("kernel" if system_info.version.major in [6, 7] else "kernel-core")

        kernel_sys_cfg = kernel_sys_cfg.replace("DEFAULTKERNEL=" + kernel_to_change, new_kernel_str)
        utils.store_content_to_file("/etc/sysconfig/kernel", kernel_sys_cfg)
        loggerinst.info("Boot kernel %s was changed to %s" % (kernel_to_change, new_kernel_str))
    else:
        loggerinst.debug("Boot kernel validated.")


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
    if system_info.version.major < 8 or system_info.arch == "s390x":
        # Applicable only on systems derived from RHEL 8 and later, and systems using GRUB2 (s390x uses zipl)
        return

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
    # OL renames some of the kernel packages by adding "-uek" (Unbreakable
    # Enterprise Kernel), e.g. kernel-uek-devel instead of kernel-devel. Such
    # package names need to be mapped to the RHEL kernel package names to have
    # them installed on the converted system.
    ol_kernel_ext = "-uek"
    pkg_names = [p.name.replace(ol_kernel_ext, "", 1) for p in additional_pkgs]
    for name in set(pkg_names):
        if name != "kernel":
            loggerinst.info("Installing RHEL %s" % name)
            call_yum_cmd("install %s" % name)


def update_rhel_kernel():
    """In the corner case where the original system kernel version is the same as the latest available RHEL kernel,
    convert2rhel needs to install older RHEL kernel version first. In this function, RHEL kernel is updated to the
    latest available version.
    """
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

    if os.path.isfile(_VERSIONLOCK_FILE_PATH) and os.path.getsize(_VERSIONLOCK_FILE_PATH) > 0:
        loggerinst.warning("YUM/DNF versionlock plugin is in use. It may cause the conversion to fail.")
        loggerinst.info("Upon continuing, we will clear all package version locks.")
        utils.ask_to_continue()

        versionlock_file.backup()

        loggerinst.info("Clearing package versions locks...")
        call_yum_cmd("versionlock clear", print_output=False)
    else:
        loggerinst.info("Usage of YUM/DNF versionlock plugin not detected.")


def has_duplicate_repos_across_disablerepo_enablerepo_options():

    duplicate_repos = set(tool_opts.disablerepo) & set(tool_opts.enablerepo)
    if duplicate_repos:
        message = "Duplicate repositories were found across disablerepo and enablerepo options:"
        for repo in duplicate_repos:
            message += "\n%s" % repo
        message += "\nThis ambiguity may have unintended consequences."
        loggerinst.warning(message)
