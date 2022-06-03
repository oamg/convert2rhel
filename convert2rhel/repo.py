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

import logging
import os
import shutil

from convert2rhel.systeminfo import system_info
from convert2rhel.utils import BACKUP_DIR, DATA_DIR


DEFAULT_YUM_REPOFILE_DIR = "/etc/yum.repos.d/"
loggerinst = logging.getLogger(__name__)


def get_rhel_repoids():
    """Get IDs of the Red Hat CDN repositories that correspond to the current system.

    In case the to-be-converted-OS minor version corresponds to RHEL Extended Update Support (EUS) release,
    we preferably enable the RHEL EUS repoids as those provide security updates over two years, in comparison to 6 months
    in case of the standard non-EUS repoids.
    """

    if system_info.corresponds_to_rhel_eus_release():
        repos_needed = system_info.eus_rhsm_repoids
    else:
        repos_needed = system_info.default_rhsm_repoids

    loggerinst.info("RHEL repository IDs to enable: %s" % ", ".join(repos_needed))

    return repos_needed


def backup_yum_repos():
    """Backup .repo files in /etc/yum.repos.d/ so the repositories can be restored on rollback."""
    loggerinst.info("Backing up .repo files from %s." % DEFAULT_YUM_REPOFILE_DIR)
    repo_files_backed_up = False
    for repo in os.listdir(DEFAULT_YUM_REPOFILE_DIR):
        if repo.endswith(".repo") and repo != "redhat.repo":
            repo_path = os.path.join(DEFAULT_YUM_REPOFILE_DIR, repo)
            shutil.copy2(repo_path, BACKUP_DIR)
            loggerinst.debug("Backed up .repo file: %s" % repo_path)
            repo_files_backed_up = True
    if not repo_files_backed_up:
        loggerinst.info("No .repo files backed up.")
    return


def restore_yum_repos():
    """Rollback all .repo files in /etc/yum.repos.d/ that were backed up."""
    loggerinst.task("Rollback: Restore .repo files to /etc/yum.repos.d/")
    repo_has_restored = False
    for repo in os.listdir(BACKUP_DIR):
        if repo.endswith(".repo"):
            repo_path_from = os.path.join(BACKUP_DIR, repo)
            repo_path_to = os.path.join("/etc/yum.repos.d/", repo)
            shutil.move(repo_path_from, repo_path_to)
            loggerinst.info("Restored .repo file: %s" % (repo))
            repo_has_restored = True

    if not repo_has_restored:
        loggerinst.info("No .repo files to rollback")


def get_hardcoded_repofiles_dir():
    """Get the path to the hardcoded repofiles for CentOS/Oracle Linux.

    We use hardcoded original vendor repofiles to be able to check whether the system is updated before the conversion.
    To be able to download backup of packages before we remove them, we can't rely on the repofiles available on
    the system.

    :return: The return can be either the path to the eus repos, or None, meaning we don't have any hardcoded repo files.
    :rtype: str | None
    """
    hardcoded_repofiles = os.path.join(
        DATA_DIR,
        "repos/%s-%s.%s"
        % (
            system_info.id,
            system_info.version.major,
            system_info.version.minor,
        ),
    )
    if os.path.exists(hardcoded_repofiles):
        return hardcoded_repofiles

    return None
