# -*- coding: utf-8 -*-
#
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

import logging
import os

from convert2rhel import exceptions, utils
from convert2rhel.backup import RestorableChange, remove_pkgs

# Fine to import call_yum_cmd for now, but we really should figure out a way to
# split this out.
from convert2rhel.pkghandler import call_yum_cmd
from convert2rhel.systeminfo import system_info


loggerinst = logging.getLogger(__name__)

# Dirctory to temporarily store yum repo configuration to download rhs packages
# from
_RHSM_TMP_DIR = os.path.join(utils.TMP_DIR, "rhsm")

# Directory to temporarily store rpms to be installed
_SUBMGR_RPMS_DIR = os.path.join(utils.DATA_DIR, "subscription-manager")

# Configuration of the repository to get Red Hat created packages for RHEL7
# from before we have access to all of RHEL.
_UBI_7_REPO_CONTENT = (
    "[ubi-7-convert2rhel]\n"
    "name=Red Hat Universal Base Image 7 - added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi/server/7/7Server/$basearch/os/\n"
    "gpgcheck=1\n"
    "enabled=1\n"
)
# Path to the repository file that we store the RHEL7-compatible repo file.
_UBI_7_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_7.repo")

# Configuration of the repository to get Red Hat created packages for RHEL8
# from before we have access to all of RHEL
# We are using UBI 8 instead of CentOS Linux 8 because there's a bug in subscription-manager-rhsm-certificates on CentOS Linux 8
# https://bugs.centos.org/view.php?id=17907
_UBI_8_REPO_CONTENT = (
    "[ubi-8-baseos-convert2rhel]\n"
    "name=Red Hat Universal Base Image 8 - BaseOS added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi8/8/$basearch/baseos/os/\n"
    "gpgcheck=1\n"
    "enabled=1\n"
)
# Path to the repository file that we store the RHEL8-compatible repo file.
_UBI_8_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_8.repo")

_UBI_9_REPO_CONTENT = (
    "[ubi-9-baseos-convert2rhel]\n"
    "name=Red Hat Universal Base Image 9 - BaseOS added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi9/9/$basearch/baseos/os/\n"
    "gpgcheck=1\n"
    "enabled=1\n"
)
_UBI_9_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_9.repo")


class RestorablePackageSet(RestorableChange):
    """Install a set of packages in a way that they can be uninstalled later.

    .. warn:: This functionality is incomplete (These are things that need cleanup)
        Installing and restoring packagesets are very complex. This class needs work before it is
        generic for any set of packages. It currently hardcodes values that are specific to
        downloading subscription-manager and how we do that.

        Implementing it in a half-ready state because we need it to install and remove
        subscription-manager rpms at the right time relative to unregistering the system. As such,
        this class relies heavily on the implementation of downloading and installing
        subscription-manager. To make this generic, some pieces of that will need to move into
        this class:

        * Need a generic way to specify the UBI_X_REPO_PATH and UBI_X_REPO_CONTENT vars. Parameters
          to __init__?  Parameter to install pkgs from "symbolic name" (vendor, pre-rhel, rhel,
          enablerepos)? which we map to specific repo configurations?
        * Backup and restore the vendor versions of packages which are in update_pkgs.
        * Rename the global variables for SUBMGR_RPS_DIR, _RHSM_TMP_DIR, _UBI_7_REPO_CONTENT,
          _UBI_7_REPO_PATH, _UBI_8_REPO_CONTENT, _UBI_8_REPO_PATH to more generic names
        * Rename the helper functions: _download_rhsm_pkgs, _log_rhsm_download_directory_contents,
          exit_on_failed_download
        * Is the "We're using distro-sync" comment wrong?  We are using install, not distro-sync and
          git log never shows us using distro-sync.
        * This class is useful for package installation but not package removal. To replace backup.ChangedRPMPackagesController and back.RestorablePackage, we need to implement removal as well.  Should we do that here or in a second class?
          * Note: ChangedRPMPackagesController might still have code that deals with package replacement.  AFAIK, that can be removed entirely.  As of 1.4, there's never a time where we replace rpms and can restore them.  (Installing might upgrade dependencies from the vendor to other vendor packages).
        * Do we need to deal with dependency version issues?  With this code, if an installed dependency is an older version than the subscription-manager package we're installing needs to upgrade and the upgraded version is not present in the vendor's repo, then we will fail.
        * Do we want to filter already installed packages from the package_list in this function
          or leave it to the caller? If we leave it to the caller, then we need to backup vendor supplied previous files here and restore them on rollback. (Currently the
          caller handles this via subscription.needed_subscription_manager_pkgs().  This could cause problems if we need to do extra handling in enable/restore for packages which already exist on the system.)
        * Do we always want to pre-download the rpms and install from a directory of package files
          or do we sometimes want yum to download and install as one step? (Current caller
          doesn't care in subscription.install_rhel_subscription_manager().)
        * Why is system_info.is_rpm_installed() implemented in syste_info? Evaluate if it should be
          moved here.

    .. warn:: Some things that are not handled by this class:
        * Packages installed as a dependency on packages listed here will not be rolled back to the
          system default if we rollback the changes.
    """

    def __init__(self, pkgs_to_install, pkgs_to_update=None):
        self.pkgs_to_install = pkgs_to_install
        self.pkgs_to_update = pkgs_to_update or []
        self.installed_pkgs = []
        self.updated_pkgs = []

        super(RestorablePackageSet, self).__init__()

    def enable(self):
        if self.enabled:
            return

        self._enable()

        super(RestorablePackageSet, self).enable()

    def _enable(self):
        """
        Actually install packages.  Do it in a helper so that we always call super() even if we
        exit early.
        """
        if not self.pkgs_to_install:
            loggerinst.info("All packages were already installed")
            return

        # Note, this use of mkdir_p is secure because SUBMGR_RPMS_DIR and
        # _RHSM_TMP_DIR do not contain any path components writable by
        # a different user.
        utils.mkdir_p(_SUBMGR_RPMS_DIR)
        utils.mkdir_p(_RHSM_TMP_DIR)

        loggerinst.info("Downloading requested packages")
        all_pkgs_to_install = self.pkgs_to_install + self.pkgs_to_update

        if system_info.version.major == 7:
            _download_rhsm_pkgs(all_pkgs_to_install, _UBI_7_REPO_PATH, _UBI_7_REPO_CONTENT)
        elif system_info.version.major == 8:
            _download_rhsm_pkgs(all_pkgs_to_install, _UBI_8_REPO_PATH, _UBI_8_REPO_CONTENT)
        elif system_info.version.major == 9:
            _download_rhsm_pkgs(all_pkgs_to_install, _UBI_9_REPO_PATH, _UBI_9_REPO_CONTENT)

        # installing the packages
        rpms_to_install = [os.path.join(_SUBMGR_RPMS_DIR, filename) for filename in os.listdir(_SUBMGR_RPMS_DIR)]

        loggerinst.info("Installing subscription-manager RPMs.")
        loggerinst.debug("RPMs scheduled for installation: %s" % utils.format_sequence_as_message(rpms_to_install))

        output, ret_code = call_yum_cmd(
            # We're using distro-sync as there might be various versions of the subscription-manager pkgs installed
            # and we need these packages to be replaced with the provided RPMs from RHEL.
            command="install",
            args=rpms_to_install,
            print_output=False,
            # When installing subscription-manager packages, the RHEL repos are
            # not available yet for getting dependencies so we need to use the repos that are
            # available on the system
            enable_repos=[],
            disable_repos=[],
            # When using the original system repos, we need YUM/DNF to expand the $releasever by itself
            set_releasever=False,
        )
        if ret_code:
            loggerinst.critical_no_exit(
                "Failed to install subscription-manager packages. Check the yum output below for details:\n\n %s"
                % output
            )
            raise exceptions.CriticalError(
                id_="FAILED_TO_INSTALL_SUBSCRIPTION_MANAGER_PACKAGES",
                title="Failed to install subscription-manager packages.",
                description="convert2rhel was unable to install subscription-manager packages. These packages are required to subscribe the system and install RHEL packages.",
                diagnosis="Failed to install packages %s. Output: %s, Status: %s"
                % (utils.format_sequence_as_message(rpms_to_install), output, ret_code),
            )

        # Need to do this here instead of in pkghandler.call_yum_cmd() to avoid
        # double printing the output if an error occurred.
        loggerinst.info(output.rstrip("\n"))

        installed_pkg_names = _get_pkg_names_from_rpm_paths(rpms_to_install)
        loggerinst.info(
            "\nPackages we installed or updated:\n%s" % utils.format_sequence_as_message(installed_pkg_names)
        )

        # We could rely on these always being installed/updated when
        # self.enabled is True but putting the values into separate attributes
        # is more friendly if outside code needs to inspect the values.
        # It is tempting to use the rpms we actually installed to populate these
        # but we would have to extract both name and arch information from the
        # rpms if we do that. (for the cornercases where a pkg for one arch is
        # already installed and we have to install a different one.
        self.installed_pkgs = self.pkgs_to_install[:]
        self.updated_pkgs = self.pkgs_to_update[:]

        super(RestorablePackageSet, self).enable()

    def restore(self):
        if not self.enabled:
            return

        loggerinst.task("Convert: Remove installed RHSM packages")
        loggerinst.info("Removing set of installed pkgs: %s" % utils.format_sequence_as_message(self.installed_pkgs))
        remove_pkgs(self.installed_pkgs, backup=False, critical=False)

        super(RestorablePackageSet, self).restore()


def _download_rhsm_pkgs(pkgs_to_download, repo_path, repo_content):
    paths = None
    try:
        _log_rhsm_download_directory_contents(_SUBMGR_RPMS_DIR, "before RHEL rhsm packages download")
        utils.store_content_to_file(filename=repo_path, content=repo_content)
        paths = utils.download_pkgs(pkgs_to_download, dest=_SUBMGR_RPMS_DIR, reposdir=_RHSM_TMP_DIR)
        _log_rhsm_download_directory_contents(_SUBMGR_RPMS_DIR, "after RHEL rhsm packages download")
    except (OSError, IOError) as err:
        loggerinst.warning("OSError({0}): {1}".format(err.errno, err.strerror))
    except SystemExit as e:
        loggerinst.critical_no_exit(
            "Unable to download the subscription-manager package and its dependencies. See details of"
            " the failed yumdownloader call above. These packages are necessary for the conversion"
            " unless you use the --no-rhsm option."
        )
        raise exceptions.CriticalError(
            id_="FAILED_TO_DOWNLOAD_SUBSCRIPTION_MANAGER_PACKAGES",
            title="Failed to download subscription-manager package and its dependencies.",
            description="To be able to subscribe the system to Red Hat we need the subscription-manager package and its dependencies to do so. Without these packages we cannot subscribe the system and we cannot install Red Hat Enterprise Linux packages.",
            diagnosis="Failed to download subscription-manager package %s." % (str(e)),
        )

    # TODO(r0x0d): Probably we need to check if paths is not empty before
    # reaching this point. There are a couple of cases where this could happen
    # and it would be ideal if we took care of that before reaching the point
    # where we try this if statement.
    if None in paths:
        loggerinst.critical_no_exit(
            "Unable to download the subscription-manager package or its dependencies. See details of"
            " the failed yumdownloader call above. These packages are necessary for the conversion"
            " unless you use the --no-rhsm option."
        )
        raise exceptions.CriticalError(
            id_="FAILED_TO_DOWNLOAD_SUBSCRIPTION_MANAGER_PACKAGES",
            title="Failed to download subscription-manager package and its dependencies.",
            description="To be able to subscribe the system to Red Hat we need the subscription-manager package and its dependencies to do so. Without these packages we cannot subscribe the system and we cannot install Red Hat Enterprise Linux packages.",
        )


def _log_rhsm_download_directory_contents(directory, when_message):
    pkgs = ["<download directory does not exist>"]
    if os.path.isdir(directory):
        pkgs = os.listdir(directory)
    loggerinst.debug(
        "Contents of %s directory %s:\n%s",
        directory,
        when_message,
        "\n".join(pkgs),
    )


def _get_pkg_names_from_rpm_paths(rpm_paths):
    """Return names of packages represented by locally stored rpm packages.
    :param rpm_paths: List of rpm with filepaths.
    :type rpm_paths: list[str]
    :return: A list of package names extracted from the rpm filepath.
    :rtype: list
    """
    pkg_names = []
    for rpm_path in rpm_paths:
        pkg_names.append(utils.get_package_name_from_rpm(rpm_path))
    return pkg_names
