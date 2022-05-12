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
import re

from collections import namedtuple
from time import sleep

from convert2rhel import pkghandler, utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


loggerinst = logging.getLogger(__name__)

SUBMGR_RPMS_DIR = os.path.join(utils.DATA_DIR, "subscription-manager")
_RHSM_TMP_DIR = os.path.join(utils.TMP_DIR, "rhsm")
_CENTOS_6_REPO_CONTENT = (
    "[centos-6-contrib-convert2rhel]\n"
    "name=CentOS Linux 6 - Contrib added by Convert2RHEL\n"
    "baseurl=https://vault.centos.org/centos/6/contrib/$basearch/\n"
    "gpgcheck=0\n"
    "enabled=1\n"
)
_CENTOS_6_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "centos_6.repo")
_UBI_7_REPO_CONTENT = (
    "[ubi-7-convert2rhel]\n"
    "name=Red Hat Universal Base Image 7 - added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi/server/7/7Server/$basearch/os/\n"
    "gpgcheck=0\n"
    "enabled=1\n"
)
_UBI_7_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_7.repo")
# We are using UBI 8 instead of CentOS Linux 8 because there's a bug in subscription-manager-rhsm-certificates on CentOS Linux 8
# https://bugs.centos.org/view.php?id=17907
_UBI_8_REPO_CONTENT = (
    "[ubi-8-baseos-convert2rhel]\n"
    "name=Red Hat Universal Base Image 8 - BaseOS added by Convert2RHEL\n"
    "baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi8/8/$basearch/baseos/os/\n"
    "gpgcheck=0\n"
    "enabled=1\n"
)
_UBI_8_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_8.repo")
MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE = 3
# Using a delay that could help when the RHSM/Satellite server is overloaded.
# The delay in seconds is a prime number that roughly doubles with each attempt.
REGISTRATION_ATTEMPT_DELAYS = [5, 11, 23]


_SUBMGR_PKG_REMOVED_IN_CL_85 = "subscription-manager-initial-setup-addon"


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
    """Unregister the system from RHSM."""
    loggerinst.info("Unregistering the system.")
    if tool_opts.keep_rhsm:
        loggerinst.info("Skipping due to the use of --keep-rhsm.")
        return

    # We are calling run_subprocess with rpm here because of a bug in
    # Oracle/CentOS Linux 7 in which the process always exits with 1 in case of a
    # rollback when KeyboardInterrupt is raised.  To avoid many changes and
    # different conditionals to handle that, we are doing a simple call to rpm to verify if
    # subscription-manager is installed on the system.  This is the current line
    # in `rpm` that causes the process to exit with any interaction with the yum
    # library
    # https://github.com/rpm-software-management/rpm/blob/rpm-4.11.x/lib/rpmdb.c#L640
    _, ret_code = utils.run_subprocess(["rpm", "--quiet", "-q", "subscription-manager"])
    if ret_code != 0:
        loggerinst.info("The subscription-manager package is not installed.")
        return
    unregistration_cmd = ["subscription-manager", "unregister"]
    output, ret_code = utils.run_subprocess(unregistration_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.warning("System unregistration failed with return code %d and message:\n%s", ret_code, output)
    else:
        loggerinst.info("System unregistered successfully.")


def register_system():
    """Register OS using subscription-manager."""

    # Loop the registration process until successful registration
    attempt = 0
    while True and attempt < MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE:
        registration_cmd = get_registration_cmd()

        attempt_msg = ""
        if attempt > 0:
            attempt_msg = "Attempt %d of %d: " % (attempt + 1, MAX_NUM_OF_ATTEMPTS_TO_SUBSCRIBE)
        loggerinst.info("%sRegistering the system using subscription-manager ...", attempt_msg)

        output, ret_code = call_registration_cmd(registration_cmd)
        if ret_code == 0:
            # Handling a signal interrupt that was previously handled by
            # subscription-manager.
            if "user interrupted process" in output.lower():
                raise KeyboardInterrupt
            return
        loggerinst.info("System registration failed with return code = %s" % str(ret_code))
        if tool_opts.credentials_thru_cli:
            loggerinst.warning(
                "Error: Unable to register your system with subscription-manager using the provided credentials."
            )
        else:
            loggerinst.info("Trying again - provide username and password.")
            tool_opts.username = None
            tool_opts.password = None
        sleep(REGISTRATION_ATTEMPT_DELAYS[attempt])
        attempt += 1
    loggerinst.critical("Unable to register the system through subscription-manager.")


def get_registration_cmd():
    """Build a command for subscription-manager for registering the system."""
    loggerinst.info("Building subscription-manager command ... ")
    registration_cmd = ["subscription-manager", "register", "--force"]

    loggerinst.info("Checking for activation key ...")
    if tool_opts.activation_key:
        # Activation key has been passed
        # -> username/password not required
        # -> organization required
        loggerinst.info("    ... activation key detected: %s" % tool_opts.activation_key)

        # TODO: Parse the output of 'subscription-manager orgs' and let the
        # user choose from the available organizations. If there's just one,
        # pick it automatically.
        # Organization is required when activation key is used
        if tool_opts.org:
            loggerinst.info("    ... org detected")

        org = tool_opts.org
        while not org:
            org = utils.prompt_user("Organization: ")

        registration_cmd.extend(("--activationkey=%s" % tool_opts.activation_key, "--org=%s" % org))
    else:
        loggerinst.info("    ... activation key not found, username and password required")

        if tool_opts.username:
            loggerinst.info("    ... username detected")

        username = tool_opts.username
        while not username:
            username = utils.prompt_user("Username: ")

        if tool_opts.password:
            loggerinst.info("    ... password detected")

        password = tool_opts.password
        while not password:
            password = utils.prompt_user("Password: ", password=True)

        registration_cmd.extend(("--username=%s" % username, "--password=%s" % password))

    if tool_opts.serverurl:
        loggerinst.debug("    ... using custom RHSM URL")
        registration_cmd.append("--serverurl=%s" % tool_opts.serverurl)

    return registration_cmd


def call_registration_cmd(registration_cmd):
    """Wrapper for run_subprocess that avoids leaking password in the log."""
    loggerinst.debug("Calling command '%s'" % hide_password(" ".join(registration_cmd)))
    return utils.run_subprocess(registration_cmd, print_cmd=False)


def hide_password(cmd):
    """Replace plaintext password with asterisks."""
    return re.sub('--password=".*?"', '--password="*****"', cmd)


def replace_subscription_manager():
    """Remove any previously installed subscription-manager packages and install the RHEL ones.

    Make sure the system is unregistered before removing the subscription-manager as not doing so would leave the
    system to be still registered on the server side, making it dificult for an admin to unregister it afterwards.
    """
    if tool_opts.keep_rhsm:
        loggerinst.info("Skipping due to the use of --keep-rhsm.")
        return

    if not os.path.isdir(SUBMGR_RPMS_DIR) or not os.listdir(SUBMGR_RPMS_DIR):
        loggerinst.critical("The %s directory does not exist or is empty." % SUBMGR_RPMS_DIR)

    unregister_system()
    remove_original_subscription_manager()
    install_rhel_subscription_manager()


def remove_original_subscription_manager():
    loggerinst.info("Removing installed subscription-manager/katello-ca-consumer packages.")
    # python3-subscription-manager-rhsm, dnf-plugin-subscription-manager, subscription-manager-rhsm-certificates, etc.
    submgr_pkgs = pkghandler.get_installed_pkg_objects("*subscription-manager*")
    # Satellite-server related package
    submgr_pkgs += pkghandler.get_installed_pkg_objects("katello-ca-consumer*")
    if not submgr_pkgs:
        loggerinst.info("No packages related to subscription-manager installed.")
        return
    loggerinst.info(
        "Upon continuing, we will uninstall the following subscription-manager/katello-ca-consumer packages:\n"
    )
    pkghandler.print_pkg_info(submgr_pkgs)
    utils.ask_to_continue()
    submgr_pkg_names = [pkg.name for pkg in submgr_pkgs]

    if system_info.id == "centos" and system_info.version.major == 8 and system_info.version.minor == 5:
        if _SUBMGR_PKG_REMOVED_IN_CL_85 in submgr_pkg_names:
            # The package listed in _SUBMGR_PKG_REMOVED_IN_CL_85 has been
            # removed from CentOS Linux 8.5 and causes conversion to fail if
            # it's installed on that system because it's not possible to back it up.
            # https://bugzilla.redhat.com/show_bug.cgi?id=2046292
            utils.remove_pkgs([_SUBMGR_PKG_REMOVED_IN_CL_85], backup=False, critical=False)
            submgr_pkg_names.remove(_SUBMGR_PKG_REMOVED_IN_CL_85)

    # Remove any oter subscription-manager packages present on the system
    utils.remove_pkgs(submgr_pkg_names, critical=False)


def install_rhel_subscription_manager():
    loggerinst.info("Checking for subscription-manager RPMs.")
    rpms_to_install = [os.path.join(SUBMGR_RPMS_DIR, filename) for filename in os.listdir(SUBMGR_RPMS_DIR)]

    if not rpms_to_install:
        loggerinst.warning("No RPMs found in %s." % SUBMGR_RPMS_DIR)
        return

    # These functions have to be called before installation of the
    # subscription-manager packages, otherwise
    # `pkghandler.filter_installed_pkgs()` would return every single package
    # that is listed in `rpms_to_install` and we don't want this to happen. We
    # want to know about the packages that were installed before the
    # installation of subscription-manager.
    pkg_names = pkghandler.get_pkg_names_from_rpm_paths(rpms_to_install)
    pkgs_to_not_track = pkghandler.filter_installed_pkgs(pkg_names)

    loggerinst.info("Installing subscription-manager RPMs.")
    _, ret_code = pkghandler.call_yum_cmd(
        # We're using distro-sync as there might be various versions of the subscription-manager pkgs installed
        # and we need these packages to be replaced with the provided RPMs from RHEL.
        command="install",
        args=rpms_to_install,
        print_output=True,
        # When installing subscription-manager packages, the RHEL repos are not available yet => we need to use
        # the repos that are available on the system
        enable_repos=[],
        disable_repos=[],
        # When using the original system repos, we need YUM/DNF to expand the $releasever by itself
        set_releasever=False,
    )
    if ret_code:
        loggerinst.critical("Failed to install subscription-manager packages. See the above yum output for details.")

    loggerinst.info("\nPackages installed:\n%s" % "\n".join(rpms_to_install))

    track_installed_submgr_pkgs(pkg_names, pkgs_to_not_track)


def track_installed_submgr_pkgs(installed_pkg_names, pkgs_to_not_track):
    """Tracking newly installed subscription-manager pkgs to be able to remove them during a rollback if needed.

    :param installed_pkg_names: List of packages that were installed on the system.
    :type installed_pkg_names: list[str]
    :param pkgs_to_not_track: List of packages that needs to be removed from tracking.
    :type pkgs_to_not_track: list[str]
    """
    pkgs_to_track = []
    for installed_pkg in installed_pkg_names:
        if installed_pkg not in pkgs_to_not_track:
            pkgs_to_track.append(installed_pkg)
        else:
            # Don't track packages that were present on the system before the installation
            loggerinst.debug("Skipping tracking previously installed package: %s" % installed_pkg)

    loggerinst.debug("Tracking installed packages: %r" % pkgs_to_track)
    utils.changed_pkgs_control.track_installed_pkgs(pkgs_to_track)


def attach_subscription():
    """Attach a specific subscription to the registered OS. If no
    subscription ID has been provided through command line, let the user
    interactively choose one.
    """
    # TODO: Support attaching multiple pool IDs.

    if tool_opts.activation_key:
        loggerinst.info("Using the activation key provided through the command line...")
        return True
    pool = ["subscription-manager", "attach"]
    if tool_opts.auto_attach:
        pool.append("--auto")
        loggerinst.info("Auto-attaching compatible subscriptions to the system ...")
    elif tool_opts.pool:
        # The subscription pool ID has been passed through a command line
        # option
        pool.extend(["--pool", tool_opts.pool])
        loggerinst.info("Attaching provided subscription pool ID to the system ...")
    else:
        subs_list = get_avail_subs()

        if len(subs_list) == 0:
            loggerinst.warning("No subscription available for the conversion.")
            return False

        elif len(subs_list) == 1:
            sub_num = 0
            loggerinst.info(
                " %s is the only subscription available, it will automatically be selected for the conversion."
                % subs_list[0].pool_id
            )

        else:
            # Let the user choose the subscription appropriate for the conversion
            loggerinst.info("Manually select subscription appropriate for the conversion")
            print_avail_subs(subs_list)
            sub_num = utils.let_user_choose_item(len(subs_list), "subscription")
            loggerinst.info("Attaching subscription with pool ID %s to the system ..." % subs_list[sub_num].pool_id)

        pool.extend(["--pool", subs_list[sub_num].pool_id])
    _, ret_code = utils.run_subprocess(pool)

    if ret_code != 0:
        # Unsuccessful attachment, e.g. the pool ID is incorrect or the
        # number of purchased attachments has been depleted.
        loggerinst.critical("Unsuccessful attachment of a subscription.")
    return True


def get_avail_subs():
    """Get list of all the subscriptions available to the user so they are
    accessible by index once the user chooses one.
    """
    # Get multiline string holding all the subscriptions available to the
    # logged-in user
    subs_raw, ret_code = utils.run_subprocess(["subscription-manager", "list", "--available"], print_output=False)
    if ret_code != 0:
        loggerinst.critical("Unable to get list of available subscriptions:\n%s" % subs_raw)
    return list(get_sub(subs_raw))


def get_sub(subs_raw):
    """Generator that provides subscriptions available to a logged-in user."""
    # Split all the available subscriptions per one subscription
    for sub_raw in re.findall(r"Subscription Name.*?Type:\s+\w+\n\n", subs_raw, re.DOTALL | re.MULTILINE):
        pool_id = get_pool_id(sub_raw)
        yield namedtuple("Sub", ["pool_id", "sub_raw"])(pool_id, sub_raw)


def get_pool_id(sub_raw_attrs):
    """Parse the input multiline string holding subscription attributes to distill the pool ID."""
    pool_id = re.search(r"^Pool ID:\s+(.*?)$", sub_raw_attrs, re.MULTILINE | re.DOTALL)
    if pool_id:
        return pool_id.group(1)

    loggerinst.critical("Cannot parse the subscription pool ID from string:\n%s" % sub_raw_attrs)


def print_avail_subs(subs):
    """Print the subscriptions available to the user so they can choose one."""
    loggerinst.info("Choose one of your subscriptions that is to be used for converting this system to RHEL:")
    for index, sub in enumerate(subs):
        index += 1
        loggerinst.info("\n======= Subscription number %d =======\n\n%s" % (index, sub.sub_raw))


def get_avail_repos():
    """Get list of all the repositories (their IDs) currently available for
    the registered system through subscription-manager.
    """
    repos_raw, _ = utils.run_subprocess(["subscription-manager", "repos"], print_output=False)
    return list(get_repo(repos_raw))


def get_repo(repos_raw):
    """Generator that parses the raw string of available repositores and
    provides the repository IDs, one at a time.
    """
    for repo_id in re.findall(r"Repo ID:\s+(.*?)\n", repos_raw, re.DOTALL | re.MULTILINE):
        yield repo_id


def verify_rhsm_installed():
    """Make sure that subscription-manager has been installed."""
    if not pkghandler.get_installed_pkg_objects("subscription-manager"):
        if tool_opts.keep_rhsm:
            loggerinst.critical(
                "When using the --keep-rhsm option, the subscription-manager needs to be installed before"
                " executing convert2rhel."
            )
        else:
            # Most probably this condition will not be hit. If the installation of subscription-manager fails, the
            # conversion stops already at that point.
            loggerinst.critical("The subscription-manager package is not installed correctly.")
    else:
        loggerinst.info("subscription-manager installed correctly.")


def disable_repos():
    """Before enabling specific repositories, all repositories should be
    disabled. This can be overriden by the --disablerepo option.
    """
    disable_cmd = ["subscription-manager", "repos"]
    disable_repos = []
    for repo in tool_opts.disablerepo:
        disable_repos.append("--disable=%s" % repo)

    if not disable_repos:
        # Default is to disable all repos to make clean environment for
        # enabling repos later
        disable_repos.append("--disable=*")

    disable_cmd.extend(disable_repos)
    output, ret_code = utils.run_subprocess(disable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repos were not possible to disable through subscription-manager:\n%s" % output)
    loggerinst.info("Repositories disabled.")
    return


def enable_repos(rhel_repoids):
    """By default, enable the standard Red Hat CDN RHEL repository IDs using subscription-manager.
    This can be overriden by the --enablerepo option.
    """
    if tool_opts.enablerepo:
        repos_to_enable = tool_opts.enablerepo
    else:
        repos_to_enable = rhel_repoids

    enable_cmd = ["subscription-manager", "repos"]
    for repo in repos_to_enable:
        enable_cmd.append("--enable=%s" % repo)
    output, ret_code = utils.run_subprocess(enable_cmd, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Repos were not possible to enable through subscription-manager:\n%s" % output)
    loggerinst.info("Repositories enabled through subscription-manager")

    system_info.submgr_enabled_repos = repos_to_enable


def rollback():
    """Rollback subscription related changes"""
    try:
        loggerinst.task("Rollback: RHSM-related actions")
        unregister_system()
    except OSError:
        loggerinst.warn("subscription-manager not installed, skipping")


def check_needed_repos_availability(repo_ids_needed):
    """Check whether all the RHEL repositories needed for the system
    conversion are available through subscription-manager.
    """
    loggerinst.info("Verifying needed RHEL repositories are available ... ")
    avail_repos = get_avail_repos()
    loggerinst.info("Repositories available through RHSM:\n%s" % "\n".join(avail_repos) + "\n")

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
        loggerinst.info("Needed RHEL repos are available.")


def download_rhsm_pkgs():
    """Download all the packages necessary for a successful registration to the Red Hat Subscription Management.

    The packages are available in non-standard repositories, so additional repofiles need to be used. The downloaded
    RPMs are to be installed in a later stage of the conversion.
    """
    if tool_opts.keep_rhsm:
        loggerinst.info("Skipping due to the use of --keep-rhsm.")
        return
    utils.mkdir_p(_RHSM_TMP_DIR)
    pkgs_to_download = ["subscription-manager", "subscription-manager-rhsm-certificates"]

    if system_info.version.major == 6:
        pkgs_to_download.append("subscription-manager-rhsm")
        _download_rhsm_pkgs(pkgs_to_download, _CENTOS_6_REPO_PATH, _CENTOS_6_REPO_CONTENT)

    elif system_info.version.major == 7:
        pkgs_to_download += ["subscription-manager-rhsm", "python-syspurpose"]
        _download_rhsm_pkgs(pkgs_to_download, _UBI_7_REPO_PATH, _UBI_7_REPO_CONTENT)

    elif system_info.version.major == 8:
        pkgs_to_download += [
            "python3-subscription-manager-rhsm",
            "dnf-plugin-subscription-manager",
            "python3-syspurpose",
            "python3-cloud-what",
            "json-c.x86_64",  # there's also an i686 version which we don't need
        ]
        _download_rhsm_pkgs(pkgs_to_download, _UBI_8_REPO_PATH, _UBI_8_REPO_CONTENT)


def _download_rhsm_pkgs(pkgs_to_download, repo_path, repo_content):
    downloaddir = os.path.join(utils.DATA_DIR, "subscription-manager")
    utils.store_content_to_file(filename=repo_path, content=repo_content)
    paths = utils.download_pkgs(pkgs_to_download, dest=downloaddir, reposdir=_RHSM_TMP_DIR)
    exit_on_failed_download(paths)


def exit_on_failed_download(paths):
    if None in paths:
        loggerinst.critical(
            "Unable to download the subscription-manager package or its dependencies. See details of"
            " the failed yumdownloader call above. These packages are necessary for the conversion"
            " unless you use the --no-rhsm option."
        )
