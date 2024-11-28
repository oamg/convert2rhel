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

__metaclass__ = type


import tempfile
import re

from contextlib import closing

from six.moves import urllib

from convert2rhel import exceptions
from convert2rhel.logger import root_logger
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import TMP_DIR, store_content_to_file
from convert2rhel.pkgmanager import TYPE, call_yum_cmd


DEFAULT_YUM_REPOFILE_DIR = "/etc/yum.repos.d"
DEFAULT_YUM_VARS_DIR = "/etc/yum/vars"
DEFAULT_DNF_VARS_DIR = "/etc/dnf/vars"

logger = root_logger.getChild(__name__)


def get_rhel_repoids():
    """Get IDs of the Red Hat CDN repositories that correspond to the current system.

    In case the to-be-converted-OS minor version corresponds to RHEL Extended Update Support (EUS) or
    RHEL Extended Lifecycle Support (ELS) release,  we preferably enable the RHEL EUS or ELS repoids respectively as
    those provide security updates over two years, in comparison to 6 months in case of the standard
    non-EUS/non-ELS repoids.
    """
    if system_info.eus_system:
        repos_needed = system_info.eus_rhsm_repoids
    elif system_info.els_system:
        repos_needed = system_info.els_rhsm_repoids
    else:
        repos_needed = system_info.default_rhsm_repoids

    logger.info("RHEL repository IDs to enable: {}".format(", ".join(repos_needed)))

    return repos_needed


class DisableReposDuringAnalysis(object):
    _instance = None
    _repos_to_disable = None

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super(DisableReposDuringAnalysis, cls).__new__(cls)
            # Cannot call the _set_rhel_repos_to_disable() directly due Python 2 support
            cls._instance._initialized = False

        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._set_rhel_repos_to_disable()
        self._instance._initialized = True

    def _set_rhel_repos_to_disable(self):
        """Set the list of repositories which should be disabled when performing pre-conversion checks.

        Avoid using RHEL repos for certain re-conversion analysis phase operations such as:
         - downloading a package backup
         - the package up-to-date check
         - querying what repository local packages have been installed from
         - the latest available kernel check
        Only the original system vendor repos should be used for these pre-conversion analysis phase operations.

        .. note::
            If --enablerepo switch is used together with the --no-rhsm, we will return a combination of repositories to
            disable as following:

            >>> # tool_opts.enablerepo comes from the CLI option `--enablerepo`.
            >>> self.repos_to_disable = ["rhel*"]
            >>> self.repos_to_disable.extend(tool_opts.enablerepo) # returns: ["rhel*", "my-rhel-repo-mirror"]

        :return: List of repoids to disable, such as ["rhel*", "my-optional-repo"]
        :rtype: List
        """
        # RHELC-884 disable the RHEL repos to avoid reaching them when checking original system.
        self._repos_to_disable = ["rhel*"]

        # this is for the case where the user configures e.g. [my-rhel-repo-mirror] on the system and leaves it enabled
        # before running convert2rhel - we want to prevent the checks from accessing it as it contains packages for RHEL
        if tool_opts.no_rhsm and tool_opts.enablerepo:
            logger.debug("Preparing a list of RHEL repositories to be disabled during analysis.")
            self._set_custom_repos()

        return self._repos_to_disable

    def _set_custom_repos(self):
        """If we are using the YUM pkg manager, we need to check if all custom repositories provided by the user through
        --enablerepo are accessible. DNF package manager can handle situation of unreachable repo by skipping it."""
        if TYPE == "dnf":
            self._repos_to_disable.extend(tool_opts.enablerepo)
            return

        # pkg manager is yum
        # copy the enablerepo list to avoid changing the original one
        repos_to_check = list(tool_opts.enablerepo)
        self._repos_to_disable.extend(_get_valid_custom_repos(repos_to_check))

    def get_rhel_repos_to_disable(self):
        """See the docstring of _set_rhel_repos_to_disable for details about the repos to disable."""
        return self._repos_to_disable


def _get_valid_custom_repos(repos_to_check):
    """Check if provided repo IDs are accessible. The function is recursive.

    :arg repos_to_check: Repo IDs to be checked
    :arg type: List
    :return: Accessible repositories
    :rtype: List
    """
    if not repos_to_check:
        return []

    args = ["-v", "--setopt=*.skip_if_unavailable=False"]
    output, ret_code = call_yum_cmd(
        command="makecache", args=args, print_output=False, disable_repos=repos_to_check, enable_repos=[]
    )

    if ret_code:
        reponame_regex = r"Error getting repository data for ([^,]+),"
        problematic_reponame_line = re.search(reponame_regex, output)
        if problematic_reponame_line:
            reponame = problematic_reponame_line.group(1)
            logger.debug(
                "Removed the {reponame} repository from the list of repositories to disable in certain"
                " pre-conversion analysis checks as it is inaccessible at the moment and yum fails when trying to"
                " disable an inaccessible repository.".format(reponame=reponame)
            )
            repos_to_check.remove(reponame)
            return _get_valid_custom_repos(repos_to_check)

    # The list of repositories passed to the function sans the inaccessible ones
    return repos_to_check


def get_rhel_disable_repos_command(disable_repos):
    """Build command containing all the repos to disable. The result looks like
    '--disablerepo repo --disablerepo repo1 --disablerepo repo2'
    If provided list is empty, empty string is returned.

    :param disable_repos: List of repo IDs to disable
    :type disable_repos: List[str]
    :return: String for disabling the rhel and user provided repositories while performing checks.
    :rtype: list[str]
    """
    if not disable_repos:
        return []

    disable_repo_command = ["".join("--disablerepo=" + repo) for repo in disable_repos]

    return disable_repo_command


def download_repofile(repofile_url):
    """Download a repository file from a specific URL.

    :raises exceptions.CriticalError: When the repository file URL is inaccessible.
    :returns str: Contents of the repofile if successfully downloaded.
    """
    try:
        with closing(urllib.request.urlopen(repofile_url, timeout=15)) as response:
            contents = response.read()

            if not contents:
                description = "The requested repository file seems to be empty. No content received when checking for url: {}".format(
                    repofile_url
                )
                logger.critical_no_exit(description)
                raise exceptions.CriticalError(
                    id_="REPOSITORY_FILE_EMPTY_CONTENT",
                    title="No content available in a repository file",
                    description=description,
                )

            logger.info("Successfully downloaded a repository file from {}.".format(repofile_url))
            return contents.decode()
    except urllib.error.URLError as err:
        raise exceptions.CriticalError(
            id_="DOWNLOAD_REPOSITORY_FILE_FAILED",
            title="Failed to download a repository file",
            description="Failed to download a repository file from {}.".format(repofile_url),
            diagnosis="Reason: {}.".format(err.reason),
        )


def write_temporary_repofile(contents):
    """Store a temporary repository file inside the :py:TMP_DIR folder.

    :param contents str: The contents to write to the file
    :returns: The path to the temporary repofile. If failed to write the
        repofile, it will return None.

    :raises exceptions.CriticalError: In case of not being able to write the
        repository contents to a file.
    """
    try:
        repofile_dir = tempfile.mkdtemp(prefix="downloaded_repofiles.", dir=TMP_DIR)
    except (OSError, IOError) as err:
        raise exceptions.CriticalError(
            id_="CREATE_TMP_DIR_FOR_REPOFILES_FAILED",
            title="Failed to create a temporary directory",
            description="Failed to create a temporary directory for storing a repository file under {}.\n"
            "Reason: {}".format(TMP_DIR, str(err)),
        )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".repo", delete=False, dir=repofile_dir) as f:
        try:
            store_content_to_file(filename=f.name, content=contents)
            return f.name
        except (OSError, IOError) as err:
            raise exceptions.CriticalError(
                id_="STORE_REPOFILE_FAILED",
                title="Failed to store a repository file",
                description="Failed to write a repository file contents to {}.\n" "Reason: {}".format(f.name, str(err)),
            )
