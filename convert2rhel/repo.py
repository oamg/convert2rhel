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

import logging
import tempfile

from contextlib import closing

from six.moves import urllib

from convert2rhel import exceptions
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import TMP_DIR, store_content_to_file


DEFAULT_YUM_VARS_DIR = "/etc/yum/vars"
DEFAULT_DNF_VARS_DIR = "/etc/dnf/vars"

loggerinst = logging.getLogger(__name__)


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

    loggerinst.info("RHEL repository IDs to enable: %s" % ", ".join(repos_needed))

    return repos_needed


def get_rhel_repos_to_disable():
    """Get the list of repositories which should be disabled when performing pre-conversion checks. Avoid downloading
    backup and up-to-date checks from them. The output list can looks like:
    ['rhel*', 'user-provided', 'user-provided1']

    :return: List of repositories to disable when performing checks.
    :rtype: List[str]
    """
    # RHELC-884 disable the RHEL repos to avoid reaching them when checking original system.
    # Also disable repositories enabled by the user for the conversion.
    return ["rhel*"] + tool_opts.enablerepo


def get_rhel_disable_repos_command(disable_repos):
    """Build command containing all the repos for disable. The result looks like
    '--disablerepo repo --disablerepo repo1 --disablerepo repo2'
    If provided list is empty, empty string is returned.

    :param disable_repos: List of repo IDs to disable
    :type disable_repos: List[str]
    :return: String for disabling the rhel and user provided repositories while performing checks.
    :rtype: str
    """
    if not disable_repos:
        return ""

    disable_repo_command = " ".join("--disablerepo=" + repo for repo in disable_repos)

    return disable_repo_command


def download_repofile(repofile_url):
    """Download the official repofile pointing to a convert2rhel repository.

    :raises exceptions.CriticalError: ...
    :returns str: Path to a successfully downloaded repofile
    """
    try:
        with closing(urllib.request.urlopen(repofile_url, timeout=15)) as response:
            filepath = write_temporary_repofile(contents=response.read())
            if filepath:
                loggerinst.info("Successfully downloaded the requested repofile from %s." % repofile_url)

            return filepath
    except urllib.error.URLError as err:
        raise exceptions.CriticalError(
            id_="DOWNLOAD_REPOSITORY_FILE_FAILED",
            title="Failed to download repository file",
            description="Failed to download the requested repository file from %s.\n"
            "Reason: %s" % (repofile_url, err.reason),
        )


def write_temporary_repofile(contents):
    """ """
    repofile_dir = tempfile.mkdtemp(prefix="convert2rhel_repo.", dir=TMP_DIR)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".repo", delete=False, dir=repofile_dir) as f:
        try:
            store_content_to_file(filename=f.name, content=contents)
            return f.name
        except (OSError, IOError) as err:
            loggerinst.warning("OSError({0}): {1}".format(err.errno, err.strerror))
