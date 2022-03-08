import logging
import os
import shutil

from convert2rhel import toolopts
from convert2rhel.repo import get_hardcoded_repofiles_dir
from convert2rhel.utils import BACKUP_DIR, TMP_DIR, download_pkg, remove_orphan_folders, run_subprocess


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
        """Track packages installed  before the PONR to be able to remove them later (roll them back) if needed."""
        self.installed_pkgs += pkgs

    def backup_and_track_removed_pkg(self, pkg):
        """Add a removed RPM pkg to the list of removed pkgs."""
        restorable_pkg = RestorablePackage(pkg)
        restorable_pkg.backup()
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
            loggerinst.info("No package to install")
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
                return False

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
            loggerinst.warning("%s hasn't been backed up" % self.filepath)
            return
        try:
            shutil.copy2(backup_filepath, self.filepath)
        except (OSError, IOError) as err:
            # Do not call 'critical' which would halt the program. We are in
            # a rollback phase now and we want to rollback as much as possible.
            # IOError for py2 and OSError for py3
            loggerinst.warning("Error(%s): %s" % (err.errno, err.strerror))
            return
        loggerinst.info("File %s restored" % self.filepath)


class RestorablePackage(object):
    def __init__(self, pkgname):
        self.name = pkgname
        self.path = None

    def backup(self):
        """Save version of RPM package"""
        loggerinst.info("Backing up %s" % self.name)
        if os.path.isdir(BACKUP_DIR):
            hardcoded_reposdir = get_hardcoded_repofiles_dir()
            reposdir = None
            if os.path.exists(hardcoded_reposdir) and toolopts.no_rhsm:
                reposdir = hardcoded_reposdir

            # When backing up the packages, the original system repofiles are still available and for them we can't
            # use the releasever for RHEL repositories
            self.path = download_pkg(self.name, dest=BACKUP_DIR, set_releasever=False, reposdir=reposdir)
        else:
            loggerinst.warning("Can't access %s" % TMP_DIR)


def remove_pkgs(pkgs_to_remove, backup=True, critical=True):
    """Remove packages not heeding to their dependencies."""

    # NOTE(r0x0d): This function is tied to the class ChangedRPMPackagesController and
    # a couple of other places too, ideally, we should decide if we want to use
    # this function as an entrypoint or the variable `changed_pkgs_control`, so
    # we can move this piece of code to the `pkghandler.py` where it should be.
    # Right now, if we move this code to the `pkghandler.py`, we have a
    # *circular import dependency error*.
    # @abadger has an implementation in mind to address some of those issues
    # and actually place a controller in front of classes like this.
    if backup:
        # Some packages, when removed, will also remove repo files, making it
        # impossible to access the repositories to download a backup. For this
        # reason we first backup all packages and only after that we remove
        for nvra in pkgs_to_remove:
            changed_pkgs_control.backup_and_track_removed_pkg(nvra)

    if not pkgs_to_remove:
        loggerinst.info("No package to remove")
        return

    for nvra in pkgs_to_remove:
        loggerinst.info("Removing package: %s" % nvra)
        _, ret_code = run_subprocess(["rpm", "-e", "--nodeps", nvra])
        if ret_code != 0:
            if critical:
                loggerinst.critical("Error: Couldn't remove %s." % nvra)
            else:
                loggerinst.warning("Couldn't remove %s." % nvra)


changed_pkgs_control = ChangedRPMPackagesController()  # pylint: disable=C0103
