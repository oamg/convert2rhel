# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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

import abc
import logging
import os
import re
import shutil

import six

from convert2rhel import utils
from convert2rhel.repo import get_hardcoded_repofiles_dir
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import BACKUP_DIR, download_pkg, remove_orphan_folders, run_subprocess


loggerinst = logging.getLogger(__name__)


class ChangedRPMPackagesController(object):
    """Keep control of installed/removed RPM pkgs for backup/restore."""

    def __init__(self):
        self.installed_pkgs = []
        self.removed_pkgs = []

    def track_installed_pkg(self, pkg):
        """Add a installed RPM pkg to the list of installed pkgs."""
        self.installed_pkgs.append(pkg)

    def track_installed_pkgs(self, pkgs):
        """Track packages installed before the PONR to be able to remove them later (roll them back) if needed."""
        self.installed_pkgs += pkgs

    def backup_and_track_removed_pkg(
        self,
        pkg,
        reposdir=None,
        set_releasever=False,
        custom_releasever=None,
        varsdir=None,
    ):
        """Add a removed RPM pkg to the list of removed pkgs."""
        restorable_pkg = RestorablePackage(pkg)
        restorable_pkg.backup(
            reposdir=reposdir,
            set_releasever=set_releasever,
            custom_releasever=custom_releasever,
            varsdir=varsdir,
        )
        self.removed_pkgs.append(restorable_pkg)

    def _remove_installed_pkgs(self):
        """For each package installed during conversion remove it."""
        loggerinst.task("Rollback: Removing installed packages")
        remove_pkgs(self.installed_pkgs, backup=False, critical=False)

    def _install_removed_pkgs(self):
        """For each package removed during conversion install it."""
        loggerinst.task("Rollback: Installing removed packages")
        pkgs_to_install = []
        for restorable_pkg in self.removed_pkgs:
            if restorable_pkg.path is None:
                loggerinst.warning("Couldn't find a backup for %s package." % restorable_pkg.name)
                continue
            pkgs_to_install.append(restorable_pkg.path)

        self._install_local_rpms(pkgs_to_install, replace=True, critical=False)

    def _install_local_rpms(self, pkgs_to_install, replace=False, critical=True):
        """Install packages locally available."""

        if not pkgs_to_install:
            loggerinst.info("No package to install.")
            return False

        cmd_param = ["rpm", "-i"]
        if replace:
            cmd_param.append("--replacepkgs")

        loggerinst.info("Installing packages:")
        for pkg in pkgs_to_install:
            loggerinst.info("\t%s" % pkg)

        cmd = cmd_param + pkgs_to_install
        output, ret_code = run_subprocess(cmd, print_output=False)
        if ret_code != 0:
            pkgs_as_str = " ".join(pkgs_to_install)
            loggerinst.debug(output.strip())
            if critical:
                loggerinst.critical("Error: Couldn't install %s packages." % pkgs_as_str)

            loggerinst.warning("Couldn't install %s packages." % pkgs_as_str)
            return False

        for path in pkgs_to_install:
            nvra, _ = os.path.splitext(os.path.basename(path))
            self.track_installed_pkg(nvra)

        return True

    def restore_pkgs(self):
        """Restore system to the original state."""
        self._remove_installed_pkgs()
        remove_orphan_folders()
        self._install_removed_pkgs()


class BackupController(object):
    """
    Controls backup and restore for all restorable types.

    This is the second version of a backup controller.  It handles all types of things that
    convert2rhel will change on the system which it can restore in case of a failure before the
    Point-of-no-return (PONR).

    The basic interface to this is a LIFO stack.  When a Restorable is pushed
    onto the stack, it is backed up.  When it is popped off of the stack, it is
    restored.  Changes are restored in the reverse order that that they were
    added.  Changes cannot be retrieved and restored out of order.
    """

    def __init__(self):
        self._restorables = []

    def push(self, restorable):
        """
        Enable a RestorableChange and track it in case it needs to be restored.

        :arg restorable: RestorableChange object that can be restored later.
        """
        if not isinstance(restorable, RestorableChange):
            raise TypeError("`%s` is not a RestorableChange object" % restorable)

        restorable.enable()

        self._restorables.append(restorable)

    def pop(self):
        """
        Restore and then return the last RestorableChange added to the Controller.

        :returns: RestorableChange object that was last added.
        :raises IndexError: If there are no RestorableChanges currently known to the Controller.
        """
        try:
            restorable = self._restorables.pop()
        except IndexError as e:
            # Use a more specific error message
            args = list(e.args)
            args[0] = "No backups to restore"
            e.args = tuple(args)
            raise e

        restorable.restore()

        return restorable

    def pop_all(self):
        """
        Restores all RestorableChanges known to the Controller and then returns them.

        :returns: List of RestorableChange objects that were known to the Controller.
        :raises IndexError: If there are no RestorableChanges currently known to the Controller.

        After running, the Controller object will not know about any RestorableChanges.
        """
        restorables = self._restorables

        if not restorables:
            raise IndexError("No backups to restore")

        # We want to restore in the reverse order the changes were enabled.
        for restorable in reversed(restorables):
            restorable.restore()

        # Reset the internal storage in case we want to use it again
        self._restorables = []

        # Now that we know everything succeeded, reverse the list that we return to the user
        restorables.reverse()

        return restorables


@six.add_metaclass(abc.ABCMeta)
class RestorableChange(object):
    """
    Interface definition for types which can be restored.
    """

    @abc.abstractmethod
    def __init__(self):
        self.enabled = False

    @abc.abstractmethod
    def enable(self):
        """
        Backup should be idempotent.  In other words, it should know if the resource has already
        been backed up and refuse to do so a second time.
        """
        self.enabled = True

    @abc.abstractmethod
    def restore(self):
        """
        Restore the state of the system.
        """
        self.enabled = False


class RestorableRpmKey(RestorableChange):
    """Import a GPG key into rpm in a reversible fashion."""

    def __init__(self, keyfile):
        """
        Setup a RestorableRpmKey to reflect the GPG key in a file.

        :arg keyfile: Filepath for a GPG key.  The RestorableRpmKey instance will be able to import
            this into the rpmdb when enabled and remove it when restored.
        """
        super(RestorableRpmKey, self).__init__()
        self.previously_installed = None
        self.keyfile = keyfile
        self.keyid = utils.find_keyid(keyfile)

    def enable(self):
        """Ensure that the GPG key has been imported into the rpmdb."""
        # For idempotence, do not back this up if we've already done so.
        if self.enabled:
            return

        if not self.installed:
            output, ret_code = utils.run_subprocess(["rpm", "--import", self.keyfile], print_output=False)
            if ret_code != 0:
                raise utils.ImportGPGKeyError("Failed to import the GPG key %s: %s" % (self.keyfile, output))

            self.previously_installed = False
            loggerinst.info("GPG key %s imported", self.keyid)

        else:
            self.previously_installed = True

        super(RestorableRpmKey, self).enable()

    @property
    def installed(self):
        """Whether the GPG key has been imported into the rpmdb."""
        output, status = utils.run_subprocess(["rpm", "-q", "gpg-pubkey-%s" % self.keyid], print_output=False)

        if status == 0:
            return True

        if status == 1 and "package gpg-pubkey-%s is not installed" % self.keyid in output:
            return False

        raise utils.ImportGPGKeyError(
            "Searching the rpmdb for the gpg key %s failed: Code %s: %s" % (self.keyid, status, output)
        )

    def restore(self):
        """Ensure the rpmdb has or does not have the GPG key according to the state before we ran."""
        if self.enabled and self.previously_installed is False:
            utils.run_subprocess(["rpm", "-e", "gpg-pubkey-%s" % self.keyid])

        super(RestorableRpmKey, self).restore()


class RestorableFile(object):
    def __init__(self, filepath):
        self.filepath = filepath

    def backup(self):
        """Save current version of a file"""
        loggerinst.info("Backing up %s." % self.filepath)
        if os.path.isfile(self.filepath):
            try:
                loggerinst.debug("Copying %s to %s." % (self.filepath, BACKUP_DIR))
                shutil.copy2(self.filepath, BACKUP_DIR)
            except (OSError, IOError) as err:
                # IOError for py2 and OSError for py3
                loggerinst.critical("Error(%s): %s" % (err.errno, err.strerror))
        else:
            loggerinst.info("Can't find %s.", self.filepath)

    def restore(self):
        """Restore a previously backed up file"""
        backup_filepath = os.path.join(BACKUP_DIR, os.path.basename(self.filepath))
        loggerinst.task("Rollback: Restoring %s from backup" % self.filepath)

        if not os.path.isfile(backup_filepath):
            loggerinst.info("%s hasn't been backed up." % self.filepath)
            return
        try:
            shutil.copy2(backup_filepath, self.filepath)
        except (OSError, IOError) as err:
            # Do not call 'critical' which would halt the program. We are in
            # a rollback phase now and we want to rollback as much as possible.
            # IOError for py2 and OSError for py3
            loggerinst.warning("Error(%s): %s" % (err.errno, err.strerror))
            return
        loggerinst.info("File %s restored." % self.filepath)


class RestorablePackage(object):
    def __init__(self, pkgname):
        self.name = pkgname
        self.path = None

    def backup(
        self,
        reposdir=None,
        set_releasever=False,
        custom_releasever=None,
        varsdir=None,
    ):
        """Save version of RPM package.

        :param reposdir: Custom repositories directory to be used in the backup.
        :type reposdir: str
        """
        loggerinst.info("Backing up %s." % self.name)
        if os.path.isdir(BACKUP_DIR):
            # If we detect that the current system is an EUS release, then we
            # proceed to use the hardcoded_repofiles, otherwise, we use the
            # custom reposdir that comes from the method parameter. This is
            # mainly because of CentOS Linux which we have hardcoded repofiles.
            # If we ever put Oracle Linux repofiles to ship with convert2rhel,
            # them the second part of this condition can be dropped.
            if system_info.corresponds_to_rhel_eus_release() and system_info.id == "centos":
                reposdir = get_hardcoded_repofiles_dir()

            # One of the reasons we hardcode repofiles pointing to archived
            # repositories of older system minor versions is that we need to be
            # able to download an older package version as a backup. Because for
            # example the default repofiles on CentOS Linux 8.4 point only to
            # 8.latest repositories that already don't contain 8.4 packages.
            if not system_info.has_internet_access:
                if reposdir:
                    loggerinst.debug(
                        "Not using repository files stored in %s due to the absence of internet access." % reposdir
                    )
                self.path = download_pkg(
                    self.name,
                    dest=BACKUP_DIR,
                    set_releasever=set_releasever,
                    custom_releasever=custom_releasever,
                    varsdir=varsdir,
                )
            else:
                if reposdir:
                    loggerinst.debug("Using repository files stored in %s." % reposdir)
                self.path = download_pkg(
                    self.name,
                    dest=BACKUP_DIR,
                    set_releasever=set_releasever,
                    reposdir=reposdir,
                    custom_releasever=custom_releasever,
                    varsdir=varsdir,
                )
        else:
            loggerinst.warning("Can't access %s" % BACKUP_DIR)


def remove_pkgs(
    pkgs_to_remove,
    backup=True,
    critical=True,
    reposdir=None,
    set_releasever=False,
    custom_releasever=None,
    varsdir=None,
):
    """Remove packages not heeding to their dependencies."""
    # NOTE(r0x0d): This function is tied to the class
    # ChangedRPMPackagesController and a couple of other places too, ideally, we
    # should decide if we want to use this function as an entrypoint or the
    # variable `changed_pkgs_control`, so we can move this piece of code to the
    # `pkghandler.py` where it should be. Right now, if we move this code to the
    # `pkghandler.py`, we have a *circular import dependency error*. @abadger
    # has an implementation in mind to address some of those issues and actually
    # place a controller in front of classes like this.

    if not pkgs_to_remove:
        loggerinst.info("No package to remove")
        return

    if backup:
        # Some packages, when removed, will also remove repo files, making it
        # impossible to access the repositories to download a backup. For this
        # reason we first back up *all* packages and only after that we remove them.
        for nevra in pkgs_to_remove:
            changed_pkgs_control.backup_and_track_removed_pkg(
                pkg=nevra,
                reposdir=reposdir,
                set_releasever=set_releasever,
                custom_releasever=custom_releasever,
                varsdir=varsdir,
            )
    for nevra in pkgs_to_remove:
        # It's necessary to remove an epoch from the NEVRA string returned by yum because the rpm command does not
        # handle the epoch well and considers the package we want to remove as not installed. On the other hand, the
        # epoch in NEVRA returned by dnf is handled by rpm just fine.
        nvra = remove_epoch_from_yum_nevra_notation(nevra)
        loggerinst.info("Removing package: %s" % nvra)
        _, ret_code = run_subprocess(["rpm", "-e", "--nodeps", nvra])
        if ret_code != 0:
            if critical:
                loggerinst.critical("Error: Couldn't remove %s." % nvra)
            else:
                loggerinst.warning("Couldn't remove %s." % nvra)


def remove_epoch_from_yum_nevra_notation(package_nevra):
    """Remove epoch from the NEVRA string returned by yum.

    Yum prints epoch only when it's non-zero. It's printed differently by yum and dnf:
      yum - epoch before name: "7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      dnf - epoch before version: "oraclelinux-release-8:8.2-1.0.8.el8.x86_64"

    This function removes the epoch from the yum notation only.
    It's safe to pass the dnf notation string with an epoch. This function will return it as is.
    """
    epoch_match = re.search(r"^\d+:(.*)", package_nevra)
    if epoch_match:
        # Return NVRA without the found epoch
        return epoch_match.group(1)
    return package_nevra


changed_pkgs_control = ChangedRPMPackagesController()  # pylint: disable=C0103
backup_control = BackupController()
