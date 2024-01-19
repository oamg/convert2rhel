__metaclass__ = type

import logging
import os
import re

import rpm

from convert2rhel.utils import TMP_DIR
from convert2rhel.utils.term import run_cmd_in_pty


loggerinst = logging.getLogger(__name__)


def report_on_a_download_error(output, pkg):
    """
    Report on a failure to download a package we need for a complete rollback.

    :param output: Output of the yumdownloader call
    :param pkg: Name of a package to be downloaded
    """
    loggerinst.warning("Output from the yumdownloader call:\n%s" % output)

    # Note: Using toolopts here is a temporary solution. We need to
    # restructure this to raise an exception on error and have the caller
    # handle whether to use INCOMPLETE_ROLLBACK to do something for several
    # reasons:
    # (1) utils should be simple functions that take input and produce
    #     output from it. Having knowledge of things specific to the
    #     program (for instance, the environment variable that convert2rhel
    #     uses) makes the utils depend on the specific place that they are
    #     run instead.
    # (2) Where an error condition arises, they should "return" that to the
    #     caller to decide how to handle it by using an exception. Handling
    #     it inside the function ties us to one specific behaviour on
    #     error. (For instance, the incomplete rollback message here ties
    #     downloading packages and performing rollbacks. But what about
    #     downloading packages that are not tied to rollbacks. Maybe we
    #     have to download a package in order for insights or
    #     subscription-manager to run. In those cases, we either cannot use
    #     this function or we might show the user a misleading message).
    # (3) Functions in utils should be free of other dependencies within
    #     convert2rhel.  That allows us to use utils with no fear of
    #     circular dependency issues.
    # (4) Making the choices here mean that when used inside of the Action
    #     framework, we are limited to returning a FAILURE for the Action
    #     plugin whereas returning SKIP would be more accurate.
    from convert2rhel import toolopts
    from convert2rhel.systeminfo import system_info

    if toolopts.tool_opts.activity == "conversion":
        if "CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK" not in os.environ:
            loggerinst.critical(
                "Couldn't download the %s package. This means we will not be able to do a"
                " complete rollback and may put the system in a broken state.\n"
                "Check to make sure that the %s repositories are enabled"
                " and the package is updated to its latest version.\n"
                "If you would rather ignore this check set the environment variable"
                " 'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK=1'." % (pkg, system_info.name)
            )
        else:
            loggerinst.warning(
                "Couldn't download the %s package. This means we will not be able to do a"
                " complete rollback and may put the system in a broken state.\n"
                "'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK' environment variable detected, continuing"
                " conversion." % pkg
            )
    else:
        loggerinst.critical(
            "Couldn't download the %s package which is needed to do a rollback of this action."
            " Check to make sure that the %s repositories are enabled and the package is"
            " updated to its latest version.\n"
            "Note that you can choose to ignore this check when running a conversion by"
            " setting the environment variable 'CONVERT2RHEL_UNSUPPORTED_INCOMPLETE_ROLLBACK=1'"
            " but not during a pre-conversion analysis." % (pkg, system_info.name)
        )


def download_pkgs(
    pkgs,
    dest=TMP_DIR,
    reposdir=None,
    enable_repos=None,
    disable_repos=None,
    set_releasever=True,
    custom_releasever=None,
    varsdir=None,
):
    """A wrapper for the download_pkg function allowing to download multiple packages."""
    return [
        download_pkg(
            pkg,
            dest,
            reposdir,
            enable_repos,
            disable_repos,
            set_releasever,
            custom_releasever,
            varsdir,
        )
        for pkg in pkgs
    ]


def download_pkg(
    pkg,
    dest=TMP_DIR,
    reposdir=None,
    enable_repos=None,
    disable_repos=None,
    set_releasever=True,
    custom_releasever=None,
    varsdir=None,
):
    """Download an rpm using yumdownloader and return its filepath.

    This function accepts a single rpm name as a string to be downloaded through
    the yumdownloader binary.

    :param pkg: The packaged that will be downloaded.
    :type pkg: str
    :param dest: The destination to download te package. Defaults to `TMP_DIR`
    :type dest: str
    :param reposdir: The folder with custom repositories to download.
    :type reposdir: str
    :param enable_repos: The repositories to enabled during the download.
    :type enable_repos: list[str]
    :param disable_repos: The repositories to disable during the download.
    :type disable_repos: list[str]
    :param set_releasever: If it's necessary to use the releasever stored in  SystemInfo.releasever.
    :type set_releasever: bool
    :param custom_releasever: A custom releasever to use. An alternative to set_systeminfo_releasever.
    :type custom_releasever: int | str
    :param varsdir: The path to the variables directory.
    :type varsdir: str

    :return: The filepath of the downloaded package.
    :rtype: str | None
    """
    from convert2rhel.systeminfo import system_info

    loggerinst.debug("Downloading the %s package." % pkg)

    # On RHEL 7, it's necessary to invoke yumdownloader with -v, otherwise there's no output to stdout.
    cmd = ["yumdownloader", "-v", "--destdir=%s" % dest]
    if reposdir:
        cmd.append("--setopt=reposdir=%s" % reposdir)

    if isinstance(disable_repos, list):
        for repo in disable_repos:
            cmd.append("--disablerepo=%s" % repo)

    if isinstance(enable_repos, list):
        for repo in enable_repos:
            cmd.append("--enablerepo=%s" % repo)

    if set_releasever:
        if not custom_releasever and not system_info.releasever:
            raise AssertionError("custom_releasever or system_info.releasever must be set.")

        if custom_releasever:
            cmd.append("--releasever=%s" % custom_releasever)
        else:
            cmd.append("--releasever=%s" % system_info.releasever)

    if varsdir:
        cmd.append("--setopt=varsdir=%s" % varsdir)

    if system_info.version.major >= 8:
        cmd.append("--setopt=module_platform_id=platform:el" + str(system_info.version.major))

    cmd.append(pkg)

    output, ret_code = run_cmd_in_pty(cmd, print_output=False)
    if ret_code != 0:
        report_on_a_download_error(output, pkg)
        return None

    path = get_rpm_path_from_yumdownloader_output(cmd, output, dest)
    if not path:
        report_on_a_download_error(output, pkg)
        return None

    loggerinst.info("Successfully downloaded the %s package." % pkg)
    loggerinst.debug("Path of the downloaded package: %s" % path)

    return path


def get_rpm_path_from_yumdownloader_output(cmd, output, dest):
    """Parse the output of yumdownloader to get the filepath of the downloaded rpm.

    The name of the downloaded rpm is in the output of a successful yumdownloader call. The output can look like:
      RHEL 7 & 8: "vim-enhanced-8.0.1763-13.0.1.el8.x86_64.rpm     2.2 MB/s | 1.4 MB     00:00"
      RHEL 7: "using local copy of 7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      RHEL 8: "[SKIPPED] oraclelinux-release-8.2-1.0.8.el8.x86_64.rpm: Already downloaded"
    """
    if not output:
        loggerinst.warning("The output of running yumdownloader is unexpectedly empty. Command:\n%s" % cmd)
        return None

    rpm_name_match = re.search(r"\S+\.rpm", output)
    pkg_nevra_match = re.search(r"using local copy of (?:\d+:)?(\S+)", output)

    if rpm_name_match:
        path = os.path.join(dest, rpm_name_match.group(0))
    elif pkg_nevra_match:
        path = os.path.join(dest, pkg_nevra_match.group(1) + ".rpm")
    else:
        loggerinst.warning(
            "Couldn't find the name of the downloaded rpm in the output of yumdownloader.\n"
            "Command:\n%s\nOutput:\n%s" % (cmd, output)
        )
        return None

    return path


def get_package_name_from_rpm(rpm_path):
    """Return name of a package that is represented by a locally stored rpm file."""
    hdr = get_rpm_header(rpm_path)
    return hdr[rpm.RPMTAG_NAME]


def get_rpm_header(rpm_path, _open=open):
    """Return an rpm header from a locally stored rpm package."""
    ts = rpm.TransactionSet()
    # disable signature checking
    ts.setVSFlags(rpm._RPMVSF_NOSIGNATURES)
    with _open(rpm_path) as rpmfile:
        rpmhdr = ts.hdrFromFdno(rpmfile)
    return rpmhdr
