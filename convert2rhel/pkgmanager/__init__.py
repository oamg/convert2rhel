# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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

from contextlib import contextmanager

from convert2rhel import utils
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts


loggerinst = logging.getLogger(__name__)

try:
    # this is used in pkghandler.py to parse version strings in the _parse_pkg_with_yum function
    from rpmUtils.miscutils import splitFilename
    from yum import *
    from yum.callbacks import DownloadBaseCallback as DownloadProgress

    # This is added here to prevent a generic try-except in the
    # `check_package_updates()` function.
    from yum.Errors import RepoError
    from yum.rpmtrans import SimpleCliCallBack as TransactionDisplay

    TYPE = "yum"

# WARNING: if there is a bug in the yum import section, we might try to import dnf incorrectly
except ImportError as e:

    import hawkey

    from dnf import *  # pylint: disable=import-error
    from dnf.callback import Depsolve, DownloadProgress

    # This is added here to prevent a generic try-except in the
    # `check_package_updates()` function.
    from dnf.exceptions import RepoError
    from dnf.yum.rpmtrans import TransactionDisplay

    TYPE = "dnf"


def create_transaction_handler():
    """Create a new instance of TransactionHandler class.

    This function will return a new instance of the TransactionHandler abstract
    class, that will be either the YumTransactionHandler or
    DnfTransactionHandler dependening on the running system.

    :return: An instance of the TransactionHandler abstract class.
    :rtype: TransactionHandler
    """
    # This is here to prevent a recursive import on both handler classes. We
    # are doing this in this ugly way to avoid a massive refactor for the merge
    # yum transaction work, specially because this module has lots of other
    # modules that depend on this.
    # The wisest thing would be to wait on the RHELC-160 work to be started,
    # and then, refactor this function to have only one entrypoint, hence:
    # TODO(r0x0d): Refactor this as part of RHELC-160.
    if TYPE == "yum":
        from convert2rhel.pkgmanager.handlers.yum import YumTransactionHandler

        return YumTransactionHandler()

    from convert2rhel.pkgmanager.handlers.dnf import DnfTransactionHandler

    return DnfTransactionHandler()


def clean_yum_metadata():
    """Remove cached metadata from yum.

    This is to make sure that Convert2RHEL works with up-to-date data from repositories before, for instance, querying
    whether the system has the latest package versions installed, or before checking whether enabled repositories have
    accessible URLs.
    """
    # We are using run_subprocess here as an alternative to call_yum_cmd
    # which doesn't apply the correct --enablerepos option because if we call this
    # earlier in the conversion the tool doesn't initialize the necessary functions in SystemInfo.
    # The viable solution was calling the yum command as a subprocess manually
    # instead of using that function wrapper.
    output, ret_code = utils.run_subprocess(
        ("yum", "clean", "metadata", "--enablerepo=*", "--quiet"), print_output=False
    )
    loggerinst.debug("Output of yum clean metadata:\n%s" % output)

    if ret_code != 0:
        loggerinst.warning("Failed to clean yum metadata:\n%s" % output)
        return

    loggerinst.info("Cached repositories metadata cleaned successfully.")


@contextmanager
def rpm_db_lock(pkg_obj):
    """Context manager to handle rpm database termination.

    .. note::
        This context manager will only do something with an instance of
        `yum.rpmsack.RPMInstalledPackage`, as it will access specific
        properties inside that class to close the RPM DB.  pkg_obj's from
        dnf are fine to pass in but will be a no-op as dnf manages the
        lifetime of the rpm_db lock fine on its own.

    .. important::
        This context manager will be used for both yum and dnf, but only yum
        will actually do an explicit cleanup after the usage. Yum seems to need
        to do that explicitly while Dnf handles it properly.

    :param pkg_obj: Instace of a package RPM installed on the system.
    :type pkg_obj: yum.rpmsack.RPMInstalledPackage | dnf.package.Package
    """
    try:
        yield
    finally:
        # Only execute the rpmdb cleanup if the property is present inside
        # pkg_obj. That means we are dealing with yum.
        # Do a manual cleanup of the rpmdb to not leave it open as the
        # conversion goes through. This is the same strategy as YumBase() uses
        # in their `close()` method, see:
        # https://github.com/rpm-software-management/yum/blob/4ed25525ee4781907bd204018c27f44948ed83fe/yum/__init__.py#L672-L675
        if hasattr(pkg_obj, "rpmdb"):
            if pkg_obj.rpmdb:
                pkg_obj.rpmdb.ts = None
                pkg_obj.rpmdb.dropCachedData()
                pkg_obj.rpmdb = None


def call_yum_cmd(
    command,
    args=None,
    print_output=True,
    enable_repos=None,
    disable_repos=None,
    set_releasever=True,
    custom_releasever=None,
    setopts=None,
):
    """Call yum command and optionally print its output.

    .. note::

        The enable_repos and disable_repos function parameters accept lists and
        they override the default use of repos, which is:

            * --disablerepo yum option = "*" by default OR passed through a CLI
            option by the user

            * --enablerepo yum option = is the repo enabled through
            subscription-manager or based on a convert2rhel configuration file
            for the particular system OR passed through a CLI option by the
            user

    .. note::

        YUM/DNF typically expands the $releasever variable used in repofiles.
        However it fails to do so after we remove the release packages
        (centos-release, oraclelinux-release, etc.) and before the
        redhat-release package is installed.

        By default, for the above reason, we provide the --releasever option to
        each yum call. However before we remove the release package, we need
        YUM/DNF to expand the variable by itself (for that, use
        set_releasever=False).

    :params command: The command to be executed, eg: install, update,
        distro-sync...
    :type command: str
    :params args: The arguments that will be passed down to the command.
    :type args: list[str]
    :params print_output: Flag to control if the output should be displayed.
    :type print_output: bool
    :params enable_repos: List of repositories to enable during the command
        execution
    :type enable_repos: list[str]
    :params disable_repos: List of repositories to disable during the ocmmand
        execution
    :type disable_repos: list[str]
    :params set_releasever: Flag to indicate if the releasever should be set.
    :type set_releasever: bool
    :params custom_releasever: Custom releasever to be set for the repofiles
    :type custom_releasever: str
    :params setopts: List of setopts to override during command execution. This
        can override any configuration defined in /etc/yum.conf. Equivalent as
        --setopt=varsdir=/tmp.
    :type setopts: list[str]

    :raises AssertionError: Raised when custom_releasever is set but
        set_releasever is not.

    :returns tuple[str, int]: Output of the command executed and the return
        code.
    """
    args = args or []
    setopts = setopts or []

    cmd = ["yum", command, "--setopt=exclude=", "-y"]

    # The --disablerepo yum option must be added before --enablerepo,
    #   otherwise the enabled repo gets disabled if --disablerepo="*" is used
    repos_to_disable = []
    if isinstance(disable_repos, list):
        repos_to_disable = disable_repos
    else:
        repos_to_disable = tool_opts.disablerepo

    for repo in repos_to_disable:
        cmd.append("--disablerepo=%s" % repo)

    if set_releasever:
        if not custom_releasever and not system_info.releasever:
            raise AssertionError("custom_releasever or system_info.releasever must be set.")

        if custom_releasever:
            cmd.append("--releasever=%s" % custom_releasever)
        else:
            cmd.append("--releasever=%s" % system_info.releasever)

    # Without the release package installed, dnf can't determine the modularity platform ID.
    if system_info.version.major >= 8:
        cmd.append("--setopt=module_platform_id=platform:el" + str(system_info.version.major))

    repos_to_enable = []
    if isinstance(enable_repos, list):
        repos_to_enable = enable_repos
    else:
        # When using subscription-manager for the conversion, use those repos for the yum call that have been enabled
        # through subscription-manager
        repos_to_enable = system_info.get_enabled_rhel_repos()

    for repo in repos_to_enable:
        cmd.append("--enablerepo=%s" % repo)

    if setopts:
        opts = ["--setopt=%s" % opt for opt in setopts]
        cmd.extend(opts)

    cmd.extend(args)

    stdout, returncode = utils.run_subprocess(cmd, print_output=print_output)
    # handle when yum returns non-zero code when there is nothing to do
    nothing_to_do_error_exists = stdout.endswith("Error: Nothing to do\n")
    if returncode == 1 and nothing_to_do_error_exists:
        loggerinst.debug("Yum has nothing to do. Ignoring.")
        returncode = 0
    return stdout, returncode
