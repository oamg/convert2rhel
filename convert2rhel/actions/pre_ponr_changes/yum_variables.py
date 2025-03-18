# Copyright(C) 2025 Red Hat, Inc.
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
import shutil

from convert2rhel import actions
from convert2rhel import backup
from convert2rhel.backup.files import InstalledFile, RestorableFile
from convert2rhel.logger import root_logger
from convert2rhel.pkghandler import get_files_owned_by_package, get_packages_to_remove
from convert2rhel.repo import DEFAULT_DNF_VARS_DIR, DEFAULT_YUM_VARS_DIR
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts.config import loggerinst

logger = root_logger.getChild(__name__)


class BackUpYumVariables(actions.Action):
    id = "BACKUP_YUM_VARIABLES"
    # We don't make a distinction between /etc/yum/vars/ and /etc/yum/vars/ in this Action. Wherever the files are we
    # back them up.
    yum_var_dirs = [DEFAULT_DNF_VARS_DIR, DEFAULT_YUM_VARS_DIR]

    def run(self):
        """Back up yum variable files in /etc/{yum,dnf}/vars/ owned by packages that are known to install these yum
        variable files (such as system-release). We back them up to be able to restore them right after we remove these
        packages. We need to restore the variable files because we use repofiles also installed by these packages and
        yum does not allow specifying a custom directory with yum variable files. This functionality came later with dnf
        however we apply the same approach to both yum and dnf for the sake of code simplicity.
        """
        logger.task("Back up yum variables")

        super(BackUpYumVariables, self).run()

        logger.debug("Getting a list of files owned by packages affecting variables in .repo files.")
        yum_var_affecting_pkgs = get_packages_to_remove(system_info.repofile_pkgs)
        yum_var_filepaths = self._get_yum_var_files_owned_by_pkgs(
            [pkg_obj.nevra.name for pkg_obj in yum_var_affecting_pkgs]
        )

        self._back_up_var_files(yum_var_filepaths)

    def _get_yum_var_files_owned_by_pkgs(self, pkg_names):
        """Get paths of yum var files owned by the packages passed to the method."""
        pkg_owned_files = set()
        for pkg in pkg_names:
            pkg_owned_files.union(get_files_owned_by_package(pkg))  # using set() and union() to get unique paths

        # Out of all the files owned by the packages get just those in yum/dnf var dirs
        yum_var_filepaths = [path for path in pkg_owned_files if os.path.dirname(path) in self.yum_var_dirs]

        return yum_var_filepaths

    def _back_up_var_files(self, paths):
        """Back up yum variable files.

        :param paths: Paths to the variable files to back up
        :type paths: list[str]
        """
        logger.info("Backing up variables files from {}.".format(" and ".join(self.yum_var_dirs)))
        if not paths:
            logger.info("No variables files backed up.")

        for filepath in paths:
            restorable_file = RestorableFile(filepath)
            backup.backup_control.push(restorable_file)


class RestoreYumVarFiles(actions.Action):
    id = "RESTORE_YUM_VAR_FILES"
    dependencies = ("REMOVE_SPECIAL_PACKAGES",)

    def run(self):
        """Right after removing packages that own yum variable files in the REMOVE_SPECIAL_PACKAGES Action, in this
        Action we restore these files to /etc/{yum,dnf}/vars/ so that yum can use them when accessing the original
        vendor repositories (which are backed up in a temporary folder and passed to yum through the --setopt=reposdir=
        option).
        The ideal solution would be to use the --setopt=varsdir= option also for the temporary folder where yum variable
        files are backed up however the option was only introduced in dnf so it's not available in RHEL 7 and its
        derivatives. For the sake of using just one approach to simplify the codebase, we are restoring the yum variable
        files no matter the package manager.
        We use the backup controller to record that we've restored the variable files meaning that upon rollback the
        files get removed. As part of the rollback we also install beck the packages that include these files so they'll
        be present.
        TODO: These restored variable files should not be present after a successful conversion. One option is to
        enhance the backup controller to indicate that a certain activity should be rolled back not only during a rollback
        but also after a successful conversion. With such a flag we would add a new post-conversion Action to run the
        backup controller restoration but only for the activities recorded with this flag.
        """
        super(RestoreYumVarFiles, self).run()

        backed_up_yum_var_dirs = backup.get_backed_up_yum_var_dirs()
        loggerinst.task("Restoring yum variable files")
        loggerinst.info(
            "In a previous step we removed a package that might have come with yum variables and in case we"
            " need to access {} repositories (e.g. when installing dependencies of subscription-manager) we"
            " need these yum variables available.".format(system_info.name)
        )
        for orig_yum_var_dir in backed_up_yum_var_dirs:
            for backed_up_yum_var_filepath in os.listdir(backed_up_yum_var_dirs[orig_yum_var_dir]):
                try:
                    shutil.copy2(backed_up_yum_var_filepath, orig_yum_var_dir)
                    logger.debug("Copied {} from backup to {}.".format(backed_up_yum_var_filepath, orig_yum_var_dir))
                except (OSError, IOError) as err:
                    # IOError for py2 and OSError for py3
                    # Not being able to restore the yum variables might or might not cause problems down the road. No
                    # need to stop the conversion because of that. The warning message below should be enough of a clue
                    # for resolving subsequent yum errors.
                    logger.warning(
                        "Couldn't copy {} to {}. Error: {}".format(
                            backed_up_yum_var_filepath, orig_yum_var_dir, err.strerror
                        )
                    )
                    return
                restored_file = InstalledFile(
                    os.path.join(orig_yum_var_dir, os.path.basename(backed_up_yum_var_filepath))
                )
                backup.backup_control.push(restored_file)
