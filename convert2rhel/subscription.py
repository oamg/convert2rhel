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

from collections import namedtuple
import os
import re
import shutil
import logging

from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel import utils


def subscribe_system():
    """Register and attach a specific subscription to OS."""
    while True:
        register_system()
        if attach_subscription():
            break
        # Clear potentially wrong credentials
        tool_opts.username = None
        tool_opts.password = None


def unregister_system():
    """Unregister the system from RHSM"""
    loggerinst = logging.getLogger(__name__)
    unregistration_cmd = "subscription-manager unregister"
    loggerinst.task("Rollback: Unregistering the system from RHSM")
    output, ret_code = utils.run_subprocess(unregistration_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.warn("System unregistration failed with return code %d and message:\n%s", ret_code, output)
    else:
        loggerinst.info("System unregistered successfully")


def register_system():
    """Register OS using subscription-manager."""
    loggerinst = logging.getLogger(__name__)

    # Loop the registration process until successful registration
    while True:
        registration_cmd = get_registration_cmd()
        loggerinst.info("Registering system by running subscription-manager"
                        " command ... ")
        ret_code = call_registration_cmd(registration_cmd)
        if ret_code == 0:
            break
        loggerinst.info("System registration failed with return code = %s"
                        % str(ret_code))
        if tool_opts.credentials_thru_cli:
            loggerinst.critical("Error: Unable to register your system with"
                                " subscription-manager using the provided"
                                " credentials.")
        else:
            loggerinst.info("Trying again - please provide correct username"
                            " and password.")
            tool_opts.username = None
            tool_opts.password = None
    return


def get_registration_cmd():
    """Build a command for subscription-manager for registering the system."""
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Building subscription-manager command ... ")
    registration_cmd = "subscription-manager register --force"
    if tool_opts.activation_key:
        # Activation key has been passed
        # -> username/password not required
        # -> organization required
        loggerinst.info("    ... activation key detected: %s"
                        % tool_opts.activation_key)
        registration_cmd += " --activationkey=%s" % tool_opts.activation_key
    else:
        # No activation key -> username/password required
        loggerinst.info("    ... activation key not found, username and"
                        " password required")
        if tool_opts.username:
            loggerinst.info("    ... username detected")
            username = tool_opts.username
        else:
            username = utils.prompt_user("Username: ")
        if tool_opts.password:
            loggerinst.info("    ... password detected")
            password = tool_opts.password
        else:
            if tool_opts.username:
                # Hint user for which username they need to enter pswd
                loggerinst.info("Username: " + username)
            password = utils.prompt_user("Password: ", password=True)
        registration_cmd += ' --username=%s --password="%s"' % (username,
                                                                password)
        tool_opts.username = username
    if tool_opts.org:
        loggerinst.info("    ... organization detected")
        org = tool_opts.org
    elif tool_opts.activation_key:
        loggerinst.info("    ... activation key requires organization")
        # Organization is required when activation key is used
        # TODO: Parse the output of 'subscription-manager orgs' and let the
        # user choose from the available organizations. If there's just one,
        # pick it automatically.
        org = utils.prompt_user("Organization: ")
    if 'org' in locals():
        # TODO: test how this option works with org name with spaces
        registration_cmd += " --org=%s" % org
    if tool_opts.serverurl:
        loggerinst.debug("    ... using custom RHSM URL")
        registration_cmd += ' --serverurl="%s"' % tool_opts.serverurl
    return registration_cmd


def call_registration_cmd(registration_cmd):
    """Wrapper for run_subprocess that avoids leaking password in the log."""
    loggerinst = logging.getLogger(__name__)
    loggerinst.debug("Calling command '%s'" % hide_password(registration_cmd))
    _, ret_code = utils.run_subprocess(registration_cmd, print_cmd=False)
    return ret_code


def hide_password(cmd):
    """Replace plaintext password with asterisks."""
    return re.sub("--password=\".*?\"", "--password=\"*****\"", cmd)


def install_subscription_manager():
    """Install subscription-manager RPM and its dependencies."""
    loggerinst = logging.getLogger(__name__)
    sm_dir = os.path.join(utils.DATA_DIR, "subscription-manager")
    if not os.path.isdir(sm_dir) or not os.listdir(sm_dir):
        loggerinst.critical("The %s directory does not exist or is empty."
                            " Using the subscription-manager is not documented"
                            " yet. Please use the --disable-submgr option."
                            " Read more about the tool usage in the article"
                            " https://access.redhat.com/articles/2360841."
                            % sm_dir)
        return
    rpms_to_install = [os.path.join(sm_dir, x) for x in os.listdir(sm_dir)]
    if rpms_to_install:
        utils.install_pkgs(rpms_to_install, True)
        loggerinst.info("RPMs installed:\n%s" % "\n".join(rpms_to_install))
    else:
        loggerinst.info("No RPM to be installed.")
    return


def attach_subscription():
    """Attach a specific subscription to the registered OS. If no
    subscription ID has been provided through command line, let the user
    interactively choose one.
    """
    # TODO: Support attaching multiple pool IDs.
    # TODO: Support the scenario when the passed activation key attaches
    #       all the appropriate subscriptions during registration already.

    loggerinst = logging.getLogger(__name__)

    if tool_opts.activation_key:
        return True

    if tool_opts.auto_attach:
        pool = "--auto"
        tool_opts.pool = "-a"
        loggerinst.info("Auto-attaching compatible subscriptions to the system ...")
    elif tool_opts.pool:
        # The subscription pool ID has been passed through a command line
        # option
        pool = "--pool %s" % tool_opts.pool
        tool_opts.pool = pool
        loggerinst.info("Attaching provided subscription pool ID to the"
                        " system ...")
    else:
        # Let the user choose the subscription appropriate for the conversion
        loggerinst.info("Manually select subscription appropriate for the conversion")
        subs_list = get_avail_subs()
        if len(subs_list) == 0:
            loggerinst.warning("No subscription available for the conversion.")
            return False

        print_avail_subs(subs_list)
        sub_num = utils.let_user_choose_item(len(subs_list), "subscription")
        pool = "--pool " + subs_list[sub_num].pool_id
        tool_opts.pool = pool
        loggerinst.info("Attaching subscription with pool ID %s to the system ..."
                        % subs_list[sub_num].pool_id)

    _, ret_code = utils.run_subprocess("subscription-manager attach %s" % pool)
    if ret_code != 0:
        # Unsuccessful attachment, e.g. the pool ID is incorrect or the
        # number of purchased attachments has been depleted.
        loggerinst.critical("Unsuccessful attachment of a subscription.")
    return True


def get_avail_subs():
    """Get list of all the subscriptions available to the user so they are
    accessible by index once the user chooses one.
    """
    loggerinst = logging.getLogger(__name__)
    # Get multiline string holding all the subscriptions available to the
    # logged-in user
    subs_raw, ret_code = utils.run_subprocess("subscription-manager list"
                                              " --available",
                                              print_output=False)
    if ret_code != 0:
        loggerinst.critical("Unable to get list of available subscriptions:"
                            "\n%s" % subs_raw)
    return list(get_sub(subs_raw))


def get_sub(subs_raw):
    """Generator that provides subscriptions available to a logged-in user.
    """
    # Split all the available subscriptions per one subscription
    for sub_raw in re.findall(
            r"Subscription Name.*?Type:\s+\w+\n\n",
            subs_raw,
            re.DOTALL | re.MULTILINE):
        pool_id = get_pool_id(sub_raw)
        yield namedtuple('Sub', ['pool_id', 'sub_raw'])(pool_id, sub_raw)


def get_pool_id(sub_raw_attrs):
    """Parse the input multiline string holding subscription attributes to distill the pool ID.
    """
    loggerinst = logging.getLogger(__name__)
    pool_id = re.search(r"^Pool ID:\s+(.*?)$",
                        sub_raw_attrs,
                        re.MULTILINE | re.DOTALL)
    if pool_id:
        return pool_id.group(1)

    loggerinst.critical("Cannot parse the subscription pool ID from string:\n%s" % sub_raw_attrs)


def print_avail_subs(subs):
    """Print the subscriptions available to the user so they can choose one.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Choose one of your subscriptions that is to be used"
                    " for converting this system to RHEL:")
    for index, sub in enumerate(subs):
        index += 1
        loggerinst.info(
            "\n======= Subscription number %d =======\n\n%s" % (index, sub.sub_raw))


def get_avail_repos():
    """Get list of all the repositories (their IDs) currently available for
    the registered system through subscription-manager.
    """
    repos_raw, _ = utils.run_subprocess("subscription-manager repos",
                                        print_output=False)
    return list(get_repo(repos_raw))


def get_repo(repos_raw):
    """Generator that parses the raw string of available repositores and
    provides the repository IDs, one at a time.
    """
    for repo_id in re.findall(
            r"Repo ID:\s+(.*?)\n",
            repos_raw,
            re.DOTALL | re.MULTILINE):
        yield repo_id


def disable_repos():
    """Before enabling specific repositories, all repositories should be
    disabled. This can be overriden by the --disablerepo option.
    """
    loggerinst = logging.getLogger(__name__)

    disable_cmd = ""
    for repo in tool_opts.disablerepo:
        disable_cmd += " --disable=%s" % repo
    if not disable_cmd:
        # Default is to disable all repos to make clean environment for
        # enabling repos later
        disable_cmd = " --disable='*'"
    output, ret_code = utils.run_subprocess("subscription-manager repos%s"
                                            % disable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repos were not possible to disable through"
                            " subscription-manager:\n%s" % output)
    loggerinst.info("Repositories disabled.")
    return


def enable_repos(rhel_repoids):
    """By default, enable the standard Red Hat CDN RHEL repository IDs using subscription-manager.
    This can be overriden by the --enablerepo option.
    """
    loggerinst = logging.getLogger(__name__)
    if tool_opts.enablerepo:
        repos_to_enable = tool_opts.enablerepo
    else:
        repos_to_enable = rhel_repoids

    enable_cmd = ""
    for repo in repos_to_enable:
        enable_cmd += " --enable=%s" % repo
    output, ret_code = utils.run_subprocess("subscription-manager repos%s"
                                            % enable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repos were not possible to enable through"
                            " subscription-manager:\n%s" % output)
    loggerinst.info("Repositories enabled through subscription-manager")

    system_info.submgr_enabled_repos = repos_to_enable


def rename_repo_files():
    """Rename non-Red Hat .repo files in /etc/yum.repos.d/ so the repositories
    in them are not used by yum command.
    """
    loggerinst = logging.getLogger(__name__)
    repo_files_renamed = False
    exe_name = utils.get_executable_name()
    for filename in os.listdir("/etc/yum.repos.d/"):
        if filename.endswith(".repo") and filename != "redhat.repo":
            filepath_old = os.path.join("/etc/yum.repos.d/", filename)
            filepath_new = "%s.%s_renamed" % (filepath_old, exe_name)
            shutil.move(filepath_old, filepath_new)
            loggerinst.info("Renamed: %s -> %s"
                            % (filepath_old, filepath_new))
            repo_files_renamed = True
    if not repo_files_renamed:
        loggerinst.info("No .repo file renamed.")
    return


def rollback_renamed_repo_files():
    """Rollback all non-Red Hat .repo files in /etc/yum.repos.d/ that were
    renamed.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.task("Rollback: Rollback all non-Red Hat .repo files renamed in"
                    " /etc/yum.repos.d/")
    exe_name = utils.get_executable_name()
    file_restored = False
    for filename in os.listdir("/etc/yum.repos.d/"):
        if filename.endswith(".%s_renamed" % exe_name):
            filepath_old = os.path.join("/etc/yum.repos.d/", filename)
            filepath_new = os.path.splitext(filepath_old)[0]
            shutil.move(filepath_old, filepath_new)
            loggerinst.info("Renamed: %s -> %s"
                            % (filepath_old, filepath_new))
            file_restored = True

    if not file_restored:
        loggerinst.info("No .repo files to rollback")


def rollback():
    """Rollback all subscription related changes"""
    loggerinst = logging.getLogger(__name__)
    rollback_renamed_repo_files()
    try:
        unregister_system()
    except OSError:
        loggerinst.warn("subscription-manager not installed, skipping")


def check_needed_repos_availability(repo_ids_needed):
    """Check whether all the RHEL repositories needed for the system
    conversion are available through subscription-manager.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Verifying needed RHEL repositories are available ... ")
    avail_repos = get_avail_repos()
    loggerinst.info("Repositories available through RHSM:\n%s" %
                    "\n".join(avail_repos) + "\n")

    all_repos_avail = True
    for repo_id in repo_ids_needed:
        if repo_id not in avail_repos:
            # TODO: List the packages that would be left untouched
            loggerinst.warning("%s repository is not available - some packages"
                               " may not be replaced and thus not supported."
                               % repo_id)
            utils.ask_to_continue()
            all_repos_avail = False
    if all_repos_avail:
        loggerinst.info("Needed RHEL repos are available.")
