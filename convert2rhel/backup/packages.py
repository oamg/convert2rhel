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

from convert2rhel import exceptions, repo, utils
from convert2rhel.backup import BACKUP_DIR, RestorableChange

# Fine to import call_yum_cmd for now, but we really should figure out a way to
# split this out.
from convert2rhel.pkgmanager import call_yum_cmd


loggerinst = logging.getLogger(__name__)


# NOTE: Over time we want to replace this with pkghandler.RestorablePackageSet.
class RestorablePackage(RestorableChange):
    def __init__(
        self, pkgs, reposdir=None, set_releasever=False, custom_releasever=None, varsdir=None, disable_repos=None
    ):
        """
        Keep control of system packages before their removal to backup and
        restore in case of rollback.

        :param pkgs list[str]: List of packages to backup.
        :param reposdir str: If a custom repository directory location needs to
            be used, this parameter can be set with the location for it.
        :param set_releasever bool: If there is need to set the relesever while
            downloading the package with yumdownloader.
        :param custom_releasever str: Custom releasever in case it need to be
            overwritten and it differs from the `py:system_info.releasever`.
        :param varsdir str: Location to the variables directory in case the
            repository files needs to interpolate variables from those folders.
        """
        super(RestorablePackage, self).__init__()

        self.pkgs = pkgs
        self.reposdir = reposdir
        self.set_releasever = set_releasever
        self.custom_releasever = custom_releasever
        self.varsdir = varsdir

        # RHELC-884 disable the RHEL repos to avoid downloading pkg from them.
        self.disable_repos = disable_repos or repo.get_rhel_repos_to_disable()

        self._backedup_pkgs_paths = []

    def enable(self):
        """Save version of RPMs packages.

        .. note::
            If we detect that the current system is an EUS release, then we
            proceed to use the hardcoded_repofiles, otherwise, we use the
            custom reposdir that comes from the method parameter. This is
            mainly because of CentOS Linux which we have hardcoded repofiles.
            If we ever put Oracle Linux repofiles to ship with convert2rhel,
            them the second part of this condition can be dropped.

            One of the reasons we hardcode repofiles pointing to archived
            repositories of older system minor versions is that we need to be
            able to download an older package version as a backup.  Because for
            example the default repofiles on CentOS Linux 8.4 point only to
            8.latest repositories that already don't contain 8.4 packages.
        """
        # Prevent multiple backup
        if self.enabled:
            return

        if not os.path.isdir(BACKUP_DIR):
            loggerinst.warning("Can't access %s" % BACKUP_DIR)
            return

        loggerinst.info("Backing up the packages: %s." % ",".join(self.pkgs))
        loggerinst.debug("Using repository files stored in %s." % self.reposdir)

        if self.reposdir:
            # Check if the reposdir exists and if the directory is empty
            if (os.path.exists(self.reposdir) and len(os.listdir(self.reposdir)) == 0) or not os.path.exists(
                self.reposdir
            ):
                loggerinst.info("The repository directory %s seems to be empty or non-existent.")
                self.reposdir = None

        for pkg in self.pkgs:
            self._backedup_pkgs_paths.append(
                utils.download_pkg(
                    pkg=pkg,
                    dest=BACKUP_DIR,
                    disable_repos=self.disable_repos,
                    set_releasever=self.set_releasever,
                    custom_releasever=self.custom_releasever,
                    varsdir=self.varsdir,
                    reposdir=self.reposdir,
                )
            )

        # TODO(r0x0d): Maybe we want to set the enabled value only when we
        # backup something?
        # Set the enabled value
        super(RestorablePackage, self).enable()

    def restore(self):
        """Restore system to the original state."""
        if not self.enabled:
            return

        utils.remove_orphan_folders()

        loggerinst.task("Rollback: Install removed packages")
        if not self._backedup_pkgs_paths:
            loggerinst.warning("Couldn't find a backup for %s package." % ",".join(self.pkgs))
            return

        self._install_local_rpms(replace=True, critical=False)

        super(RestorablePackage, self).restore()

    def _install_local_rpms(self, replace=False, critical=True):
        """Install packages locally available."""

        if not self._backedup_pkgs_paths:
            loggerinst.info("No package to install.")
            return False

        cmd = ["rpm", "-i"]
        if replace:
            cmd.append("--replacepkgs")

        loggerinst.info("Installing packages:\t%s" % ", ".join(self.pkgs))
        for pkg in self._backedup_pkgs_paths:
            cmd.append(pkg)

        output, ret_code = utils.run_subprocess(cmd, print_output=False)
        if ret_code != 0:
            pkgs_as_str = utils.format_sequence_as_message(self.pkgs)
            loggerinst.debug(output.strip())
            if critical:
                loggerinst.critical_no_exit("Error: Couldn't install %s packages." % pkgs_as_str)
                raise exceptions.CriticalError(
                    id_="FAILED_TO_INSTALL_PACKAGES",
                    title="Couldn't install packages.",
                    description=(
                        "While attempting to roll back changes, we encountered "
                        "an unexpected failure while attempting to reinstall "
                        "one or more packages that we removed as part of the "
                        "conversion."
                    ),
                    diagnosis="Couldn't install %s packages. Command: %s Output: %s Status: %d"
                    % (pkgs_as_str, cmd, output, ret_code),
                )

            loggerinst.warning("Couldn't install %s packages." % pkgs_as_str)
            return False

        return True


class RestorablePackageSet(RestorableChange):
    """Install a set of packages in a way that they can be uninstalled later.

    .. warn:: This functionality is incomplete (These are things that need cleanup)
        Installing and restoring packagesets are very complex. This class needs work before it is
        generic for any set of packages.

        To make this generic, some pieces of that will need to move into this
        class:

        * Parameter to install pkgs from "symbolic name" (vendor, pre-rhel,
          rhel, enablerepos)? which we map to specific repo configurations?
        * Backup and restore the vendor versions of packages which are in
          update_pkgs.
        * This class is useful for package installation but not package
          removal. To replace backup.ChangedRPMPackagesController and
          back.RestorablePackage, we need to implement removal as well.  Should
          we do that here or in a second class?
        * Note: ChangedRPMPackagesController might still have code that deals
          with package replacement.  AFAIK, that can be removed entirely.  As
          of 1.4, there's never a time where we replace rpms and can restore
          them. (Installing might upgrade dependencies from the vendor to other
          vendor packages).
        * Do we need to deal with dependency version issues?  With this code,
          if an installed dependency is an older version than the
          subscription-manager package we're installing needs to upgrade and
          the upgraded version is not present in the vendor's repo, then we
          will fail.
        * Do we want to filter already installed packages from the package_list
          in this function or leave it to the caller? If we leave it to the
          caller, then we need to backup vendor supplied previous files here
          and restore them on rollback. (Currently the caller handles this via
          subscription.needed_subscription_manager_pkgs().  This could cause
          problems if we need to do extra handling in enable/restore for
          packages which already exist on the system.)
        * Why is system_info.is_rpm_installed() implemented in syste_info?
          Evaluate if it should be moved here.

    .. warn:: Some things that are not handled by this class:
        * Packages installed as a dependency on packages listed here will not be rolled back to the
          system default if we rollback the changes.
    """

    def __init__(
        self,
        pkgs_to_install,
        pkgs_to_update=None,
        enable_repos=None,
        disable_repos=None,
        set_releasever=False,
        custom_releasever=None,
        setopts=None,
    ):
        self.pkgs_to_install = pkgs_to_install
        self.pkgs_to_update = pkgs_to_update or []
        self.installed_pkgs = []
        self.updated_pkgs = []

        self.enable_repos = enable_repos or []
        self.disable_repos = disable_repos or []
        self.setopts = setopts or []

        self.set_releasever = set_releasever
        self.custom_releasever = custom_releasever

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

        loggerinst.info("Downloading requested packages")
        all_pkgs_to_install = self.pkgs_to_install + self.pkgs_to_update

        loggerinst.debug("RPMs scheduled for installation: %s" % utils.format_sequence_as_message(all_pkgs_to_install))

        output, ret_code = call_yum_cmd(
            command="install",
            args=all_pkgs_to_install,
            print_output=False,
            # When installing subscription-manager packages, the RHEL repos are
            # not available yet for getting dependencies so we need to use the
            # repos that are available on the system
            enable_repos=self.enable_repos,
            disable_repos=self.disable_repos,
            set_releasever=self.set_releasever,
            custom_releasever=self.custom_releasever,
            setopts=self.setopts,
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
                % (utils.format_sequence_as_message(all_pkgs_to_install), output, ret_code),
            )

        # Need to do this here instead of in pkghandler.call_yum_cmd() to avoid
        # double printing the output if an error occurred.
        loggerinst.info(output.rstrip("\n"))
        loggerinst.info(
            "\nPackages we installed or updated:\n%s" % utils.format_sequence_as_message(all_pkgs_to_install)
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

        loggerinst.task("Rollback: Remove installed RHSM packages")
        loggerinst.info("Removing set of installed pkgs: %s" % utils.format_sequence_as_message(self.installed_pkgs))
        utils.remove_pkgs(self.installed_pkgs, critical=False)

        super(RestorablePackageSet, self).restore()
