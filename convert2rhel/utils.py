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

import datetime
import errno
import getpass
import inspect
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import traceback

import pexpect
import rpm

from six import moves


loggerinst = logging.getLogger(__name__)


class Color(object):
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


# Absolute path of a directory holding data for this tool
DATA_DIR = "/usr/share/convert2rhel/"
# Directory for temporary data to be stored during runtime
TMP_DIR = "/var/lib/convert2rhel/"
BACKUP_DIR = os.path.join(TMP_DIR, "backup")


def format_msg_with_datetime(msg, level):
    """Return a string with msg formatted according to the level"""
    temp_date = datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    return "[%s] %s - %s", temp_date, level.upper(), msg


def get_executable_name():
    """Get name of the executable file passed to the python interpreter."""
    return os.path.basename(inspect.stack()[-1][1])


def require_root():
    if os.geteuid() != 0:
        print("The tool needs to be run under the root user.")
        print("\nNo changes were made to the system.")
        sys.exit(1)


def get_file_content(filename, as_list=False):
    """Return content of a file either as a list of lines or as a multiline
    string.
    """
    lines = []
    if not os.path.exists(filename):
        if not as_list:
            return ""
        return lines
    file_to_read = open(filename, "r")
    try:
        lines = file_to_read.readlines()
    finally:
        file_to_read.close()
    if as_list:
        # remove newline character from each line
        return [x.strip() for x in lines]

    return "".join(lines)


def store_content_to_file(filename, content):
    """Write the content into the file.

    Accept string or list of strings (in that case every string will be written
    on separate line). In case the ending blankline is missing, the newline
    character is automatically appended to the file.
    """
    if isinstance(content, list):
        content = "\n".join(content)
    if len(content) > 0 and content[-1] != "\n":
        # append the missing newline to comply with standard about text files
        content += "\n"
    file_to_write = open(filename, "w")
    try:
        file_to_write.write(content)
    finally:
        file_to_write.close()


def restart_system():
    from convert2rhel.toolopts import tool_opts

    if tool_opts.restart:
        run_subprocess("reboot")
    else:
        loggerinst.warning("In order to boot the RHEL kernel, restart of the system is needed.")


def run_subprocess(cmd="", print_cmd=True, print_output=True):
    """Call the passed command and optionally log the called command (print_cmd=True) and its
    output (print_output=True). Switching off printing the command can be useful in case it contains
    a password in plain text.
    """
    if print_cmd:
        loggerinst.debug("Calling command '%s'" % cmd)

    # Python 2.6 has a bug in shlex that interprets certain characters in a string as
    # a NULL character. This is a workaround that encodes the string to avoid the issue.
    if sys.version_info[0] == 2 and sys.version_info[1] == 6:
        cmd = cmd.encode("ascii")
    cmd = shlex.split(cmd, False)
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    output = ""
    for line in iter(process.stdout.readline, b""):
        output += line.decode()
        if print_output:
            loggerinst.info(line.decode().rstrip("\n"))

    # Call communicate() to wait for the process to terminate so that we can get the return code by poll().
    # It's just for py2.6, py2.7+/3 doesn't need this.
    process.communicate()

    return_code = process.poll()
    return output, return_code


def run_cmd_in_pty(cmd="", print_cmd=True, print_output=True, columns=120):
    """Similar to run_subprocess(), but the command is executed in a pseudo-terminal.

    The pseudo-terminal can be useful when a command prints out a different output with or without an active terminal
    session. E.g. yumdownloader does not print the name of the downloaded rpm if not executed from a terminal.
    Switching off printing the command can be useful in case it contains a password in plain text.

    :param cmd: The command to execute, including the options, e.g. "ls -al"
    :type cmd: string
    :param print_cmd: Log the command (to both logfile and stdout)
    :type print_cmd: bool
    :param print_output: Log the combined stdout and stderr of the executed command (to both logfile and stdout)
    :type print_output: bool
    :param columns: Number of columns of the pseudo-terminal (characters on a line). This may influence the output.
    :type columns: int
    :return: The output (combined stdout and stderr) and the return code of the executed command
    :rtype: tuple
    """
    if print_cmd:
        loggerinst.debug("Calling command '%s'" % cmd)

    class PexpectSizedWindowSpawn(pexpect.spawn):
        # https://github.com/pexpect/pexpect/issues/134
        def setwinsize(self, rows, cols):
            super(PexpectSizedWindowSpawn, self).setwinsize(0, columns)

    process = PexpectSizedWindowSpawn(cmd, env={"LC_ALL": "C"}, timeout=None)

    # The setting of window size is super unreliable
    process.setwinsize(0, columns)
    loggerinst.debug("Pseudo-PTY columns set to: %s" % (process.getwinsize(),))

    process.expect(pexpect.EOF)
    output = process.before.decode()
    if print_output:
        loggerinst.info(output.rstrip("\n"))

    process.close()  # Per the pexpect API, this is necessary in order to get the return code
    return_code = process.exitstatus

    return output, return_code


def let_user_choose_item(num_of_options, item_to_choose):
    """Ask user to enter a number corresponding to the item they choose."""
    while True:  # Loop until user enters a valid number
        opt_num = prompt_user("Enter number of the chosen %s: " % item_to_choose)
        try:
            opt_num = int(opt_num)
        except ValueError:
            loggerinst.warning("Enter a valid number.")
        # Ensure the entered number is in the proper range
        if 0 < opt_num <= num_of_options:
            break
        else:
            loggerinst.warning("The entered number is not in range 1 - %s." % num_of_options)
    return opt_num - 1  # Get zero-based list index


def mkdir_p(path):
    """Create all missing directories for the path and raise no exception
    if the path exists.
    """
    try:
        os.makedirs(path)
    except OSError as err:
        if err.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def ask_to_continue():
    """Ask user whether to continue with the system conversion. If no,
    execution of the tool is stopped.
    """
    from convert2rhel.toolopts import tool_opts

    if tool_opts.autoaccept:
        return
    while True:
        cont = prompt_user("\nContinue with the system conversion? [y/n]: ")
        if cont == "y":
            break
        if cont == "n":
            loggerinst.critical("User canceled the conversion\n")


def prompt_user(question, password=False):
    color_question = Color.BOLD + question + Color.END
    if password:
        response = getpass.getpass(color_question)
    else:
        response = moves.input(color_question)
    loggerinst.info("\n")
    return response


def log_traceback(debug):
    """Log a traceback either to both a file and stdout, or just file, based
    on the debug parameter.
    """
    traceback_str = get_traceback_str()
    if debug:
        # Print the traceback to the user when debug option used
        loggerinst.debug(traceback_str)
    else:
        # Print the traceback to the log file in any way
        loggerinst.file(traceback_str)


def get_traceback_str():
    """Get a traceback of an exception as a string."""
    exc_type, exc_value, exc_traceback = sys.exc_info()
    return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))


def remove_tmp_dir():
    """Remove temporary folder (TMP_DIR), not needed post-conversion."""
    try:
        shutil.rmtree(TMP_DIR)
        loggerinst.info("Temporary folder %s removed" % TMP_DIR)
    except OSError as err:
        loggerinst.warn("Failed removing temporary folder %s\nError (%s): %s" % (TMP_DIR, err.errno, err.strerror))
    except TypeError:
        loggerinst.warn("TypeError error while removing temporary folder %s" % TMP_DIR)


class DictWListValues(dict):
    """Python 2.4 replacement for Python 2.5+ collections.defaultdict(list)."""

    def __getitem__(self, item):
        if item not in iter(self.keys()):
            self[item] = []

        return super(DictWListValues, self).__getitem__(item)


class ChangedRPMPackagesController(object):
    """Keep control of installed/removed RPM pkgs for backup/restore."""

    def __init__(self):
        self.installed_pkgs = []
        self.removed_pkgs = []

    def track_installed_pkg(self, pkg):
        """Add a installed RPM pkg to the list of installed pkgs."""
        self.installed_pkgs.append(pkg)

    def track_installed_pkgs(self, pkgs):
        """Track packages installed  before the PONR to be able to remove them later (roll them back) if needed."""
        self.installed_pkgs += pkgs

    def backup_and_track_removed_pkg(self, pkg):
        """Add a removed RPM pkg to the list of removed pkgs."""
        restorable_pkg = RestorablePackage(pkg)
        restorable_pkg.backup()
        self.removed_pkgs.append(restorable_pkg)

    def _remove_installed_pkgs(self):
        """For each package installed during conversion remove it."""
        loggerinst.task("Rollback: Removing installed packages")
        remove_pkgs(self.installed_pkgs, backup=False, critical=False)

    def _install_removed_pkgs(self):
        """For each package removed during conversion install it."""
        loggerinst.task("Rollback: Installing removed packages")
        pkgs_to_install = []
        for restorable_pkg in self.removed_pkgs:
            if restorable_pkg.path is None:
                loggerinst.warning("Couldn't find a backup for %s package." % restorable_pkg.name)
                continue
            pkgs_to_install.append(restorable_pkg.path)

        install_local_rpms(pkgs_to_install, replace=True, critical=False)

    def restore_pkgs(self):
        """Restore system to the original state."""
        self._remove_installed_pkgs()
        remove_orphan_folders()
        self._install_removed_pkgs()


def remove_orphan_folders():
    """Even after removing redhat-release-* package, some of its folders are
    still present, are empty, and that blocks us from installing centos-release
    pkg back. So, by now, we are removing them manually.
    """
    rh_release_paths = [
        "/usr/share/redhat-release",
        "/usr/share/doc/redhat-release",
    ]

    def is_dir_empty(path):
        return not os.listdir(path)

    for path in rh_release_paths:
        if os.path.exists(path) and is_dir_empty(path):
            os.rmdir(path)


def remove_pkgs(pkgs_to_remove, backup=True, critical=True):
    """Remove packages not heeding to their dependencies."""

    if backup:
        # Some packages, when removed, will also remove repo files, making it
        # impossible to access the repositories to download a backup. For this
        # reason we first backup all packages and only after that we remove
        for nvra in pkgs_to_remove:
            changed_pkgs_control.backup_and_track_removed_pkg(nvra)

    if not pkgs_to_remove:
        loggerinst.info("No package to remove")
        return

    for nvra in pkgs_to_remove:
        loggerinst.info("Removing package: %s" % nvra)
        _, ret_code = run_subprocess("rpm -e --nodeps %s" % nvra)
        if ret_code != 0:
            if critical:
                loggerinst.critical("Error: Couldn't remove %s." % nvra)
            else:
                loggerinst.warning("Couldn't remove %s." % nvra)


def install_local_rpms(pkgs_to_install, replace=False, critical=True):
    """Install packages locally available."""

    if not pkgs_to_install:
        loggerinst.info("No package to install")
        return False

    cmd_param = ["rpm", "-i"]
    if replace:
        cmd_param.append("--replacepkgs")

    cmd = " ".join(cmd_param)
    pkgs = " ".join(pkgs_to_install)

    loggerinst.info("Installing packages:")
    for pkg in pkgs_to_install:
        loggerinst.info("\t%s" % pkg)

    output, ret_code = run_subprocess("%s %s" % (cmd, pkgs), print_output=False)
    if ret_code != 0:
        loggerinst.debug(output.strip())
        if critical:
            loggerinst.critical("Error: Couldn't install %s packages." % pkgs)
            return False

        loggerinst.warning("Couldn't install %s packages." % pkgs)
        return False

    for path in pkgs_to_install:
        nvra, _ = os.path.splitext(os.path.basename(path))
        changed_pkgs_control.track_installed_pkg(nvra)

    return True


def download_pkgs(
    pkgs,
    dest=TMP_DIR,
    reposdir=None,
    enable_repos=None,
    disable_repos=None,
    set_releasever=True,
):
    """A wrapper for the download_pkg function allowing to download multiple packages."""
    return [download_pkg(pkg, dest, reposdir, enable_repos, disable_repos, set_releasever) for pkg in pkgs]


def download_pkg(
    pkg,
    dest=TMP_DIR,
    reposdir=None,
    enable_repos=None,
    disable_repos=None,
    set_releasever=True,
):
    """Download an rpm using yumdownloader and return its filepath. If not successful, return None.

    The enable_repos and disable_repos function parameters accept lists. If used, the repos are passed to the
    --enablerepo and --disablerepo yumdownloader options, respectively.

    Pass just a single rpm name as a string to the pkg parameter.
    """
    from convert2rhel.systeminfo import system_info

    loggerinst.debug("Downloading the %s package." % pkg)

    # On RHEL 7, it's necessary to invoke yumdownloader with -v, otherwise there's no output to stdout.
    cmd = 'yumdownloader -v --destdir="%s"' % dest
    if reposdir:
        cmd += ' --setopt=reposdir="%s"' % reposdir

    if isinstance(disable_repos, list):
        for repo in disable_repos:
            cmd += ' --disablerepo="%s"' % repo

    if isinstance(enable_repos, list):
        for repo in enable_repos:
            cmd += ' --enablerepo="%s"' % repo

    if set_releasever and system_info.releasever:
        cmd += " --releasever=%s" % system_info.releasever

    if system_info.version.major == 8:
        cmd += " --setopt=module_platform_id=platform:el8"

    cmd += " %s" % pkg

    output, ret_code = run_cmd_in_pty(cmd, print_output=False)
    if ret_code != 0:
        loggerinst.warning(
            "Couldn't download the %s package using yumdownloader.\n"
            "Output from the yumdownloader call:\n%s" % (pkg, output)
        )
        return None

    path = get_rpm_path_from_yumdownloader_output(cmd, output, dest)
    if path:
        loggerinst.info("Successfully downloaded the %s package." % pkg)
        loggerinst.debug("Path of the downloaded package: %s" % path)

    return path


def get_rpm_path_from_yumdownloader_output(cmd, output, dest):
    """Parse the output of yumdownloader to get the filepath of the downloaded rpm.

    The name of the downloaded rpm is on the last line of the output from yumdownloader. The line can look like:
      RHEL 6 & 7 & 8: "vim-enhanced-8.0.1763-13.0.1.el8.x86_64.rpm     2.2 MB/s | 1.4 MB     00:00"
      RHEL 6: "/var/lib/convert2rhel/yum-plugin-ulninfo-0.2-13.el6.noarch.rpm already exists and appears to be complete"
      RHEL 7: "using local copy of 7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      RHEL 8: "[SKIPPED] oraclelinux-release-8.2-1.0.8.el8.x86_64.rpm: Already downloaded"
    """
    if output:
        last_output_line = output.splitlines()[-1]
    else:
        loggerinst.warning("The output of running yumdownloader is unexpectedly empty. Command:\n%s" % cmd)
        return None

    rpm_name_match = re.search(r"\S*\.rpm", last_output_line)
    pkg_nevra_match = re.search(r"^using local copy of (?:\d+:)?(.*)$", last_output_line)

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


class RestorableFile(object):
    def __init__(self, filepath):
        self.filepath = filepath

    def backup(self):
        """Save current version of a file"""
        loggerinst.info("Backing up %s" % self.filepath)
        if os.path.isfile(self.filepath):
            try:
                loggerinst.info("Copying %s to %s" % (self.filepath, BACKUP_DIR))
                shutil.copy2(self.filepath, BACKUP_DIR)
            except (OSError, IOError) as err:
                # IOError for py2 and OSError for py3
                loggerinst.critical("Error(%s): %s" % (err.errno, err.strerror))
        else:
            loggerinst.info("Can't find %s", self.filepath)

    def restore(self):
        """Restore a previously backed up file"""
        backup_filepath = os.path.join(BACKUP_DIR, os.path.basename(self.filepath))
        loggerinst.task("Rollback: Restoring %s from backup" % self.filepath)

        if not os.path.isfile(backup_filepath):
            loggerinst.warning("%s hasn't been backed up" % self.filepath)
            return
        try:
            shutil.copy2(backup_filepath, self.filepath)
        except (OSError, IOError) as err:
            # Do not call 'critical' which would halt the program. We are in
            # a rollback phase now and we want to rollback as much as possible.
            # IOError for py2 and OSError for py3
            loggerinst.warning("Error(%s): %s" % (err.errno, err.strerror))
            return
        loggerinst.info("File %s restored" % self.filepath)


class RestorablePackage(object):
    def __init__(self, pkgname):
        self.name = pkgname
        self.path = None

    def backup(self):
        """Save version of RPM package"""
        loggerinst.info("Backing up %s" % self.name)
        if os.path.isdir(BACKUP_DIR):
            # When backing up the packages, the original system repofiles are still available and for them we can't
            # use the releasever for RHEL repositories
            self.path = download_pkg(self.name, dest=BACKUP_DIR, set_releasever=False)
        else:
            loggerinst.warning("Can't access %s" % TMP_DIR)


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


def set_locale():
    """Set the POSIX default locale for the main process as well as the child processes.

    The reason is to get predictable output from the executables we call, not influenced by non-default locale.
    """
    os.environ.update({"LC_ALL": "C"})


changed_pkgs_control = ChangedRPMPackagesController()  # pylint: disable=C0103
