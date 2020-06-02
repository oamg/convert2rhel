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

"""This module provides functions that go through the installed packages
and return the following:
a) packages not available in RHEL repos,
b) RHEL repos that contain the packages.
"""

from itertools import imap
import os
import re
import logging

from convert2rhel import pkghandler
from convert2rhel import subscription
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel import utils


def package_analysis():
    """Go through the installed packages, report which packages are missing
    in RHEL repos and return in which RHEL repos the rest can be found.
    """
    loggerinst = logging.getLogger(__name__)

    repo_data_files = get_repo_data_files()
    if repo_data_files:
        loggerinst.info("Reading offline snapshot of RHEL repositories" " for %s variant" % tool_opts.variant)
        loggerinst.info("\n".join(repo_data_files) + "\n")
        rhel_repos_content = read_repo_files(repo_data_files)
        repos_needed = match_repo_pkgs_to_installed(rhel_repos_content)
        loggerinst.info("Repositories needed: %s" % "\n".join(repos_needed) + "\n")
        loggerinst.info("Listing non-%s and non-Red Hat packages ... " % system_info.name)
    else:
        loggerinst.debug("Offline snapshot of RHEL repositories not found.")
        repos_needed = [system_info.default_repository_id]
    third_party_pkgs = pkghandler.get_third_party_pkgs()
    if third_party_pkgs:
        loggerinst.warning(
            "Only packages signed by %s are to be"
            " reinstalled. Red Hat support won't be provided"
            " for the following third party packages:\n" % system_info.name
        )
        pkghandler.print_pkg_info(third_party_pkgs)
        utils.ask_to_continue()
    else:
        loggerinst.info("No third party packages installed.")
    return repos_needed


def get_repo_data_files():
    """Get list of paths to dark matrix-generated repository files."""
    path = os.path.join(utils.DATA_DIR, "repo-mapping", system_info.id)
    # Skip the files for a different variant than the one in
    # config file. Note: 'Common' files hold pkg names of all
    # variants.
    if not os.path.exists(path):
        # if path does not exists is means no repomap is installed.
        return []
    return [
        os.path.join(path, repo_file)
        for repo_file in os.listdir(path)
        if re.match("%s|Common" % tool_opts.variant, repo_file)
    ]


def read_repo_files(repo_data_files):
    """Read content of the single RHEL variant-related dark matrix-generated
    static repository files which hold information about moved, removed and
    kept packages.
    """
    rhel_repos_content = {}
    rhel_repos_content["removed"] = []
    rhel_repos_content["kept"] = []
    rhel_repos_content["moved"] = utils.DictWListValues()
    for repo_file in repo_data_files:
        if "_kept" in repo_file:
            # The repository names on the original system do not
            # match those on RHEL, except the base repo (that has no suffix,
            # like -optional). Therefore all kept packages are put into just
            # one list, basically representing just the RHEL base repo. The
            # list will serve just to complete the picture, which packages are
            # available in RHEL repos.
            # TODO: This may not be true -> implement logic to cope with repos
            # different from base repo in which the packages are 'kept'
            for pkg in utils.get_file_content(repo_file, True):
                rhel_repos_content["kept"].append(pkg.split(" kept")[0])
        if "_removed" in repo_file:
            # Put all removed packages into one list, no matter in which repo
            # they are missing. This list will be used to determine which
            # packages are not available in the RHEL repos.
            for pkg in utils.get_file_content(repo_file, True):
                rhel_repos_content["removed"].append(pkg.split(" removed")[0])
        if "_moved" in repo_file:
            # The moved packages are stored into separate dictionaries to
            # distinguish in which repository is each 'moved' package
            # available.
            moved_to = repo_file.rsplit("moved_", 1)[1]
            for pkg in utils.get_file_content(repo_file, True):
                rhel_repos_content["moved"][moved_to].append(pkg.split(" moved")[0])
    return rhel_repos_content


def match_repo_pkgs_to_installed(rhel_repos_content):
    """Determine in which RHEL repositories the installed packages are
    available and report which packages are not available in any RHEL repo.
    Return list of the needed RHEL repositories.
    """
    installed_pkgs = pkghandler.get_installed_pkgs_by_fingerprint(system_info.fingerprints_orig_os)
    pkgs = determine_pkg_availability(rhel_repos_content, installed_pkgs)
    warn_about_nonavail_pkgs(pkgs)
    supported_repos = get_supported_repos()
    repos_needed = get_repos_needed(pkgs["moved"].keys(), supported_repos)
    return repos_needed


def determine_pkg_availability(rhel_repos_content, installed_pkgs):
    """Compare list of the installed packages to the packages in RHEL repos
    (as stored in dark matrix-generated static data) to get a dictionary
    determining the availability of each installed package.
    """
    pkgs = {}
    pkgs["removed"] = []
    pkgs["kept"] = []
    pkgs["moved"] = utils.DictWListValues()

    for installed_pkg in installed_pkgs:
        if installed_pkg in rhel_repos_content["removed"]:
            pkgs["removed"].append(installed_pkg)
        if installed_pkg in rhel_repos_content["kept"]:
            pkgs["kept"].append(installed_pkg)
        for moved_to in rhel_repos_content["moved"].keys():
            if installed_pkg in rhel_repos_content["moved"][moved_to]:
                pkgs["moved"][moved_to].append(installed_pkg)
    return pkgs


def warn_about_nonavail_pkgs(pkgs):
    """Print out information about availability of the installed packages as
    related to RHEL repositories.
    """
    loggerinst = logging.getLogger(__name__)
    if pkgs["removed"]:
        loggerinst.warning(
            "The following packages were not found in the"
            " offline snapshot of RHEL repositories. \nIt may"
            " be that the snapshot is either not up-to-date or"
            " does not cover special RHEL repos that hold these"
            " packages. \nBut possibly these packages will not"
            " be replaced by the Red Hat-signed ones and"
            " therefore not supported by Red Hat:\n"
        )
        loggerinst.info("\n".join(pkgs["removed"]))
        loggerinst.info("\n")
        utils.ask_to_continue()
    return


def get_supported_repos():
    """Get a dictionary with RHEL repositories supported by dark matrix.
    Note: Mapping of the installed packages to RHEL repositories is possible
    only for the RHEL repositories processed by dark matrix - these are
    captured in the repo_minimap file.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Getting supported %s repositories ... " % tool_opts.variant)
    minimap_path = os.path.join(utils.DATA_DIR, "repo-mapping", "repo_minimap")
    minimap = utils.get_file_content(minimap_path, as_list=True)
    repos = {}
    for line in minimap:
        if tool_opts.variant not in line:
            # Skip the variants different from the chosen one
            continue
        # Save into a dictionary in format 'repo name':'repo ID'
        repos[re.match("(.+?);", line).group(1)] = re.search(";.*?;(.+?);", line).group(1)
    if not repos:
        # If there is no repos, add the default one.
        repos["Server"] = system_info.default_repository_id
    print_supported_repos(repos)
    return repos


def print_supported_repos(repos):
    """Print out those repository IDs mentioned in repo_minimap that are
    relevant to the chosen RHEL variant.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Supported %s repositories:\n" % tool_opts.variant)
    max_key_length = max(imap(len, repos))
    loggerinst.info("%-*s  %s" % (max_key_length, "Repo name", "Repo ID"))
    loggerinst.info("%-*s  %s" % (max_key_length, "-" * len("Repo name"), "-" * len("Repo ID")))
    for key, value in repos.iteritems():
        loggerinst.info("%-*s  %s" % (max_key_length, key, value))
    loggerinst.info("\n")
    return


def get_repos_needed(repo_suffixes, supported_repos):
    """Get Repository IDs of the RHEL repositories needed for the system
    conversion.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Getting repository IDs of the RHEL repositories needed" " for the system conversion ... ")
    if "" not in repo_suffixes:
        # Empty string means base repository (in the realm of dark matrix),
        # i.e. its name is equivalent to the chosen variant of RHEL. If it's
        # missing in this list it just means that no package moved from
        # specialized repo to base repo, i.e. all have been 'kept' in the base
        # repo.
        repo_suffixes.append("")
    repo_ids_list = []
    for repo_suffix in repo_suffixes:
        # Get repo name as used in the dark matrix repo_minimap, e.g.
        # Server-optional
        if repo_suffix == "":
            additional_dash = ""
        else:
            additional_dash = "-"
        repo_name = "%s%s%s" % (tool_opts.variant, additional_dash, repo_suffix)
        if repo_name in supported_repos.keys():
            repo_ids_list.append(supported_repos[repo_name])
        else:
            loggerinst.critical("Repository %s not found in repo_minimap." % repo_name)
    return repo_ids_list


def check_needed_repos_availability(repo_ids_needed):
    """Check whether all the RHEL repositories needed for the system
    conversion are available through the provided subscription.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Verifying required repositories are available ... ")
    if tool_opts.disable_submgr:
        avail_repos = get_avail_repos()
    else:
        avail_repos = subscription.get_avail_repos()

    loggerinst.info("repos available:\n%s" % "\n".join(avail_repos) + "\n")
    all_repos_avail = True
    for repo_id in repo_ids_needed:
        if repo_id not in avail_repos:
            # TODO: List the packages that would be left untouched
            loggerinst.warning(
                "%s repository is not available - some packages"
                " may not be replaced and thus not supported." % repo_id
            )
            utils.ask_to_continue()
            all_repos_avail = False
    if all_repos_avail:
        loggerinst.info("Needed repos are available.")
    return


def get_avail_repos():
    """Get list of all the repositories (their IDs) currently available for
    the registered system.
    """
    loggerinst = logging.getLogger(__name__)
    repos_raw, ret_code = pkghandler.call_yum_cmd(command="repolist -v ", print_output=False)
    if ret_code:
        loggerinst.critical("yum repolist command failed: \n\n" + repos_raw)
    line = ""
    repos = []
    repo_id_prefix = "Repo-id      : "
    for line in repos_raw.split("\n"):
        if line.startswith(repo_id_prefix):
            repo_id = line.split(repo_id_prefix)[1]
            repos.append(repo_id)

    return repos
