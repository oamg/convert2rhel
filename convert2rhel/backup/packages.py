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


import os

from convert2rhel import exceptions, repo, utils
from convert2rhel.backup import BACKUP_DIR, RestorableChange

# Fine to import call_yum_cmd for now, but we really should figure out a way to
# split this out.
from convert2rhel.logger import root_logger
from convert2rhel.pkgmanager import call_yum_cmd


logger = root_logger.getChild(__name__)


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
        self.disable_repos = disable_repos or repo.DisableReposDuringAnalysis().get_rhel_repos_to_disable()

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
            logger.warning("Can't access {}".format(BACKUP_DIR))
            return

        logger.info("Backing up the packages: {}.".format(",".join(self.pkgs)))
        logger.debug("Using repository files stored in {}.".format(self.reposdir))

        if self.reposdir:
            # Check if the reposdir exists and if the directory is empty
            if (os.path.exists(self.reposdir) and len(os.listdir(self.reposdir)) == 0) or not os.path.exists(
                self.reposdir
            ):
                logger.info("The repository directory %s seems to be empty or non-existent.")
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

        logger.task("Install removed packages")
        if not self._backedup_pkgs_paths:
            logger.warning("Couldn't find a backup for {} package.".format(",".join(self.pkgs)))
            raise exceptions.CriticalError(
                id_="FAILED_TO_INSTALL_PACKAGES",
                title="Couldn't find package backup",
                description=(
                    "While attempting to roll back changes, we encountered "
                    "an unexpected failure while we cannot find a package backup."
                ),
                diagnosis="Couldn't find a backup for {} package.".format(utils.format_sequence_as_message(self.pkgs)),
            )

        self._install_local_rpms(replace=True, critical=True)

        super(RestorablePackage, self).restore()

    def _install_local_rpms(self, replace=False, critical=True):
        """Install packages locally available."""

        if not self._backedup_pkgs_paths:
            logger.info("No package to install.")
            return False

        cmd = ["rpm", "-i"]
        if replace:
            cmd.append("--replacepkgs")

        logger.info("Installing packages:\t{}".format(", ".join(self.pkgs)))
        for pkg in self._backedup_pkgs_paths:
            cmd.append(pkg)

        output, ret_code = utils.run_subprocess(cmd, print_output=False)
        if ret_code != 0:
            pkgs_as_str = utils.format_sequence_as_message(self.pkgs)
            logger.debug(output.strip())
            if critical:
                logger.critical_no_exit("Error: Couldn't install {} packages.".format(pkgs_as_str))
                raise exceptions.CriticalError(
                    id_="FAILED_TO_INSTALL_PACKAGES",
                    title="Couldn't install packages.",
                    description=(
                        "While attempting to roll back changes, we encountered "
                        "an unexpected failure while attempting to reinstall "
                        "one or more packages that we removed as part of the "
                        "conversion."
                    ),
                    diagnosis="Couldn't install {} packages. Command: {} Output: {} Status: {}".format(
                        pkgs_as_str, cmd, output, ret_code
                    ),
                )

            logger.warning("Couldn't install {} packages.".format(pkgs_as_str))
            return False

        return True


class RestorablePackageSet(RestorableChange):
    """Install a set of packages in a way that they can be uninstalled later.

    .. warn::
        This functionality is incomplete (These are things that need cleanup)
        Installing and restoring packagesets are very complex. This class needs
        work before it is generic for any set of packages. To make this
        generic, some pieces of that will need to move into this class:

        * This class is useful for package installation but not package
        removal. To replace back.RestorablePackage, we need to implement
        removal as well.  Should we do that here or in a second class?

        * Do we need to deal with dependency version issues?  With this code,
        if an installed dependency is an older version than the
        subscription-manager package we're installing needs to upgrade and the
        upgraded version is not present in the vendor's repo, then we will
        fail.

        * Do we want to filter already installed packages from the package_list
        in this function or leave it to the caller? If we leave it to the
        caller, then we need to backup vendor supplied previous files here and
        restore them on rollback. (Currently the caller handles this via
        subscription.needed_subscription_manager_pkgs().  This could cause
        problems if we need to do extra handling in enable/restore for packages
        which already exist on the system.)

    .. warn::
        Some things that are not handled by this class:
        * Packages installed as a dependency on packages listed here will not
        be rolled back to the system default if we rollback the changes.
    """

    def __init__(
        self,
        pkgs_to_install,
        enable_repos=None,
        disable_repos=None,
        set_releasever=False,
        custom_releasever=None,
        setopts=None,
    ):
        self.pkgs_to_install = pkgs_to_install
        self.installed_pkgs = []

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
            logger.info("All packages were already installed")
            return

        formatted_pkgs_sequence = utils.format_sequence_as_message(self.pkgs_to_install)

        logger.debug("RPMs scheduled for installation: {}".format(formatted_pkgs_sequence))

        output, ret_code = call_yum_cmd(
            command="install",
            args=self.pkgs_to_install,
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
            logger.critical_no_exit(
                "Failed to install scheduled packages. Check the yum output below for details:\n\n {}".format(output)
            )
            raise exceptions.CriticalError(
                id_="FAILED_TO_INSTALL_SCHEDULED_PACKAGES",
                title="Failed to install scheduled packages.",
                description="convert2rhel was unable to install scheduled packages.",
                diagnosis="Failed to install packages {}. Output: {}, Status: {}".format(
                    formatted_pkgs_sequence, output, ret_code
                ),
            )

        # Need to do this here instead of in pkghandler.call_yum_cmd() to avoid
        # double printing the output if an error occurred.
        logger.info(output.rstrip("\n"))
        logger.info("\nPackages we installed or updated:\n{}".format(formatted_pkgs_sequence))

        # We could rely on these always being installed/updated when
        # self.enabled is True but putting the values into separate attributes
        # is more friendly if outside code needs to inspect the values.
        self.installed_pkgs = self.pkgs_to_install[:]

        super(RestorablePackageSet, self).enable()

    def restore(self):
        if not self.enabled:
            return

        logger.task("Remove installed packages")
        logger.info("Removing set of installed pkgs: {}".format(utils.format_sequence_as_message(self.installed_pkgs)))
        utils.remove_pkgs(self.installed_pkgs, critical=False)

        super(RestorablePackageSet, self).restore()
