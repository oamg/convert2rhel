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
from convert2rhel.utils import BACKUP_DIR


loggerinst = logging.getLogger(__name__)


def get_rhel_repoids():
    """Get IDs of the Red Hat CDN repositories that correspond to the current system."""
    repos_needed = system_info.default_rhsm_repoids

    loggerinst.info("RHEL repository IDs to enable: %s" % ', '.join(repos_needed))

    return repos_needed

def backup_yum_repos():
    """Backup .repo files in /etc/yum.repos.d/ so the repositories
    can be restored on rollback.
    """
    loggerinst.info("Backing up repositories")
    repo_files_backed_up = False
    for repo in os.listdir("/etc/yum.repos.d/"):
        if repo.endswith(".repo") and repo != "redhat.repo":
            repo_path = os.path.join("/etc/yum.repos.d/", repo)
            shutil.copy2(repo_path, BACKUP_DIR)
            loggerinst.info("Backed up repo: %s" % (repo_path))
            repo_files_backed_up = True
    if not repo_files_backed_up:
        loggerinst.info("No .repo files backed up.")
    return

def restore_yum_repos():
    """Rollback all .repo files in /etc/yum.repos.d/ that were
    backed up.
    """
    loggerinst.task("Rollback: Restore .repo files to /etc/yum.repos.d/")
    repo_has_restored = False
    for repo in os.listdir(BACKUP_DIR):
        if repo.endswith(".repo"):
            repo_path_from = os.path.join(BACKUP_DIR, repo)
            repo_path_to = os.path.join("/etc/yum.repos.d/", repo)
            shutil.move(repo_path_from, repo_path_to)
            loggerinst.info("Restored repo: %s" % (repo))
            repo_has_restored = True

    if not repo_has_restored:
        loggerinst.info("No .repo files to rollback")
