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
import sys
import logging
import subprocess

from convert2rhel.toolopts import tool_opts
from convert2rhel import pkghandler
from convert2rhel import utils
from convert2rhel import pkghandler
from convert2rhel.systeminfo import system_info

SUBMGR_RPMS_DIR = os.path.join(utils.DATA_DIR, "subscription-manager")
_RHSM_TMP_DIR = os.path.join(utils.TMP_DIR, "rhsm")
_CENTOS_6_REPO_CONTENT = \
        '[centos-6-contrib-convert2rhel]\n' \
        'name=CentOS 6 - Contrib added by Convert2RHEL\n' \
        'baseurl=https://vault.centos.org/centos/6/contrib/$basearch/\n' \
        'gpgcheck=0\n' \
        'enabled=1\n'
_CENTOS_6_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "centos_6.repo")
_CENTOS_7_REPO_CONTENT = \
        '[centos-7-convert2rhel]\n' \
        'name=CentOS 7 added by Convert2RHEL\n' \
        'mirrorlist=http://mirrorlist.centos.org/?release=7&arch=$basearch&repo=os\n' \
        'gpgcheck=0\n' \
        'enabled=1\n'
_CENTOS_7_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "centos_7.repo")
# We are using UBI 8 instead of CentOS 8 because there's a bug in subscription-manager-rhsm-certificates on CentOS 8
# https://bugs.centos.org/view.php?id=17907
_UBI_8_REPO_CONTENT = \
        '[ubi-8-baseos-convert2rhel]\n' \
        'name=Red Hat Universal Base Image 8 - BaseOS added by Convert2RHEL\n' \
        'baseurl=https://cdn-ubi.redhat.com/content/public/ubi/dist/ubi8/8/$basearch/baseos/os/\n' \
        'gpgcheck=0\n' \
        'enabled=1\n'
_UBI_8_REPO_PATH = os.path.join(_RHSM_TMP_DIR, "ubi_8.repo")


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
            loggerinst.info("Trying again - provide username and password.")
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


def replace_subscription_manager():
    """Remove the original and install the RHEL subscription-manager packages."""
    loggerinst = logging.getLogger(__name__)
    if not os.path.isdir(SUBMGR_RPMS_DIR) or not os.listdir(SUBMGR_RPMS_DIR):
        loggerinst.critical("The %s directory does not exist or is empty."
                            " Using the subscription-manager is not documented"
                            " yet. Please use the --disable-submgr option."
                            " Read more about the tool usage in the article"
                            " https://access.redhat.com/articles/2360841."
                            % SUBMGR_RPMS_DIR)
        return

    remove_original_subscription_manager()
    install_rhel_subscription_manager()


def remove_original_subscription_manager():
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Removing non-RHEL subscription-manager packages.")
    # python3-subscription-manager-rhsm, dnf-plugin-subscription-manager, subscription-manager-rhsm-certificates, etc.
    submgr_pkgs = pkghandler.get_installed_pkgs_w_different_fingerprint(
        system_info.fingerprints_rhel, "*subscription-manager*")
    if not submgr_pkgs:
        loggerinst.info("No packages related to subscription-manager installed.")
        return
    loggerinst.info("Upon continuing, we will uninstall the following subscription-manager pkgs:\n")
    pkghandler.print_pkg_info(submgr_pkgs)
    utils.ask_to_continue()
    submgr_pkg_names = [pkg.name for pkg in submgr_pkgs]
    utils.remove_pkgs(submgr_pkg_names, critical=False)


def install_rhel_subscription_manager():
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Installing subscription-manager RPMs.")
    rpms_to_install = [os.path.join(SUBMGR_RPMS_DIR, filename) for filename in os.listdir(SUBMGR_RPMS_DIR)]

    if not rpms_to_install:
        loggerinst.warn("No RPMs found in %s." % SUBMGR_RPMS_DIR)
        return

    _, ret_code = pkghandler.call_yum_cmd(
        # We're using distro-sync as there might be various versions of the subscription-manager pkgs installed
        # and we need these packages to be replaced with the provided RPMs from RHEL.
        "install",
        " ".join(rpms_to_install),
        # When installing subscription-manager packages, the RHEL repos are not available yet => we need to use
        # the repos that are available on the system
        enable_repos=[],
        disable_repos=[],
        # When using the original system repos, we need YUM/DNF to expand the $releasever by itself
        set_releasever=False
    )
    if ret_code:
        loggerinst.critical("Failed to install subscription-manager packages."
                            " See the above yum output for details.")
    else:
        loggerinst.info("Packages installed:\n%s" % "\n".join(rpms_to_install))


def remove_subscription_manager():
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Removing RHEL subscription-manager packages.")
    # python3-subscription-manager-rhsm, dnf-plugin-subscription-manager, subscription-manager-rhsm-certificates, etc.
    submgr_pkgs = pkghandler.get_installed_pkgs_by_fingerprint(system_info.fingerprints_rhel, "*subscription-manager*")
    if not submgr_pkgs:
        loggerinst.info("No packages related to subscription-manager installed.")
        return
    pkghandler.call_yum_cmd("remove", " ".join(submgr_pkgs), print_output=False)

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


def rollback():
    """Rollback all subscription related changes"""
    loggerinst = logging.getLogger(__name__)
    try:
        unregister_system()
        remove_subscription_manager()
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


def download_rhsm_pkgs():
    """Download all the packages necessary for a successful registration to the Red Hat Subscription Management.

    The packages are available in non-standard repositories, so additional repofiles need to be used. The downloaded
    RPMs are to be installed in a later stage of the conversion.
    """
    utils.mkdir_p(_RHSM_TMP_DIR)
    pkgs_to_download = ["subscription-manager",
                        "subscription-manager-rhsm-certificates"]

    if system_info.version.major == 6:
        pkgs_to_download.append("subscription-manager-rhsm")
        _download_rhsm_pkgs(pkgs_to_download, _CENTOS_6_REPO_PATH, _CENTOS_6_REPO_CONTENT)

    elif system_info.version.major == 7:
        pkgs_to_download += ["subscription-manager-rhsm", "python-syspurpose"]
        _download_rhsm_pkgs(pkgs_to_download, _CENTOS_7_REPO_PATH, _CENTOS_7_REPO_CONTENT)
        _get_rhsm_cert_on_centos_7()

    elif system_info.version.major == 8:
        pkgs_to_download += ["python3-subscription-manager-rhsm", "dnf-plugin-subscription-manager",
                             "python3-syspurpose"]
        _download_rhsm_pkgs(pkgs_to_download, _UBI_8_REPO_PATH, _UBI_8_REPO_CONTENT)


def _download_rhsm_pkgs(pkgs_to_download, repo_path, repo_content):
    downloaddir = os.path.join(utils.DATA_DIR, "subscription-manager")
    utils.store_content_to_file(filename=repo_path, content=repo_content)
    paths = utils.download_pkgs(pkgs_to_download, dest=downloaddir, reposdir=_RHSM_TMP_DIR)
    exit_on_failed_download(paths)


def exit_on_failed_download(paths):
    loggerinst = logging.getLogger(__name__)
    if None in paths:
        loggerinst.critical("Unable to download the subscription-manager package or its dependencies. See details of"
                            " the failed yumdownloader call above. These packages are necessary for the conversion"
                            " unless you use the --disable-submgr option.")


def _get_rhsm_cert_on_centos_7():
    """There's a RHSM-related bug on CentOS 7: https://bugs.centos.org/view.php?id=14785
    - The subscription-manager-rhsm-certificates is missing the necessary /etc/rhsm/ca/redhat-uep.pem.
    - This cert is still available in the python-rhsm-certificates package which is not possible to install
      (because it is obsoleted by the subscription-manager-rhsm-certificates).
    The workaround is to download the python-rhsm-certificates and extract the certificate from it.
    """
    loggerinst = logging.getLogger(__name__)
    cert_pkg_path = utils.download_pkg(pkg="python-rhsm-certificates", dest=_RHSM_TMP_DIR, reposdir=_RHSM_TMP_DIR)
    exit_on_failed_download([cert_pkg_path])

    output, ret_code = utils.run_subprocess("rpm2cpio %s" % cert_pkg_path, print_output=False)
    if ret_code != 0:
        loggerinst.critical("Failed to extract cpio archive from the %s package." % cert_pkg_path)

    cpio_filepath = cert_pkg_path + ".cpio"
    utils.store_content_to_file(filename=cpio_filepath, content=output)

    cert_path = "/etc/rhsm/ca/redhat-uep.pem"
    utils.mkdir_p("/etc/rhsm/ca/")
    output, ret_code = utils.run_subprocess("cpio --quiet -F %s -iv --to-stdout .%s" % (cpio_filepath, cert_path),
                                            print_output=False)
    # cpio return code 0 even if the requested file is not in the archive - but then the output is 0 chars
    if ret_code != 0 or not output:
        loggerinst.critical("Failed to extract the %s certificate from the %s archive." % (cert_path, cpio_filepath))
    utils.store_content_to_file(cert_path, output)
