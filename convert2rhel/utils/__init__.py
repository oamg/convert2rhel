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

import fcntl
import getpass
import json
import multiprocessing
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import traceback

from functools import wraps

import pexpect
import rpm

from six import moves

from convert2rhel import exceptions, i18n
from convert2rhel.logger import root_logger
from convert2rhel.toolopts import tool_opts


logger = root_logger.getChild(__name__)

# A string we're using to replace sensitive information (like an RHSM password) in logs, terminal output, etc.
OBFUSCATION_STRING = "*" * 5


class ImportGPGKeyError(Exception):
    """Raised for failures during the rpm import of gpg keys."""


class Color:
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


class UnableToSerialize(Exception):
    """
    Internal class that is used to declare that a object was not able to be
    serialized with Pickle inside the Process subclass.
    """

    pass


class Process(multiprocessing.Process):
    """Overrides the implementation of the multiprocessing.Process class.

    This class is being overriden to be able to catch all type of exceptions in
    order to not interrupt the conversion if it is not intended to. The
    original behaviour from `multiprocess.Process` is that the code running
    inside the child process will handle the exceptions, so in our case, if we
    raise SystemExit because we are using `logger.critical`, we wouldn't have a
    chance to catch that and enter the rollback.

    .. note::
        Code taken from https://stackoverflow.com/a/63773140
    """

    def __init__(self, *args, **kwargs):
        """Default constructor for the class"""
        multiprocessing.Process.__init__(self, *args, **kwargs)
        self._pconn, self._cconn = multiprocessing.Pipe()
        self._exception = None

    def run(self):
        """Overrides the `run` method to catch exceptions raised in child.

        .. important::
            Exceptions that bubble up to this point will deadlock if the
            traceback are over 64KiB in size. It is not a good idea to let
            unhandled exceptions go up this point as it could cause the threads
            to lock indefinitely.
            Link to comment: https://stackoverflow.com/questions/19924104/python-multiprocessing-handling-child-errors-in-parent/33599967#comment113491531_33599967
        """
        try:
            multiprocessing.Process.run(self)
            self._cconn.send(None)
        # Here, `SystemExit` inherits from `BaseException`, which is too
        # broad to catch as it involves for-loop exceptions. The idea here
        # is to catch `SystemExit` *and* any `Exception` that shows up as we do
        # a lot of logger.critical() and they do raise `SystemExit`.
        except (Exception, SystemExit) as e:
            try:
                import cPickle as pickle
            except ImportError:
                import pickle

            try:
                self._cconn.send(e)
            except pickle.PicklingError:
                self._cconn.send(UnableToSerialize("Child process raised {}: {}".format(type(e), str(e))))

    @property
    def exception(self):
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        return self._exception


def run_as_child_process(func):
    """Decorator to execute functions as child process.

    This decorator will use `multiprocessing.Process` class to initiate the
    function as a child process to the parent process with the intention to
    execute that in its own process, thus, avoiding cases where libraries would
    install signal handlers that could be propagated to the main thread if they
    do not do a proper clean-up.

    .. note::
        This decorator is mostly intended to be used when dealing with
        functions that call directly `rpm` or `yum`.

        In `rpm` (version 4.11.3, RHEL 7), it's known that whenever there is a
        call to that library, it will install a global signal handler catching
        different types of signals, but most importantly, the SIGINT (Ctrl + C)
        one, which causes a problem during the conversion as we can't replace
        or override that signal as it was initiated in a C library rather than
        a python library.

        By using this decorator, `rpm` will install the signal handler in the
        child process and leave the parent one with the original signal
        handling that is initiated by python itself (or, whatever signal is
        registered when the conversion starts as well).

    .. important::
        It is important to know that if a function is using this decorator,
        then it won't be possible for that function to spawn new child
        processes inside their workflow. This is a limitation imposed by the
        `daemon` property used to spawn the the first child process (the
        function being decorated), as it won't let a grandchild process being
        created inside an child process.
        For more information about that, refer to the Python Multiprocessing
        docs: https://docs.python.org/2.7/library/multiprocessing.html#multiprocessing.Process.daemon

        For example::
            # A perfect normal function that spawn a child process
            def functionB():
                ...
                multiprocessing.Process(...)

            # If we want to use this decorator in `functionB()`, we would leave the child process of `functionB()` orphans when the parent process exits.
            @utils.run_as_child_process
            def functionB():
                ...
                multiprocessing.Process(...)
                ...

    :param func: Function attached to the decorator
    :type func: Callable
    :return: A internal callable wrapper
    :rtype: Callable
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        """
        Wrapper function to execute and control the function attached to the
        decorator.

        :arg args: Arguments tied to the function
        :type args: tuple
        :keyword kwargs: Named arguments tied to the function
        :type kwargs: dict

        :raises KeyboardInterrupt: Raises a `KeyboardInterrupt` if a SIGINT is
            caught during the execution of the child process. This exception
            will be re-raised to the stack once it is caught.
        :raises Exception: Raise any general exception that can occur during
            the execution of the child process.

        :return: If the Queue is not empty, return anything in it, otherwise,
            return `None`.
        :rtype: Any
        """

        def inner_wrapper(*args, **kwargs):
            """
            Inner function wrapper to execute decorated functions without the
            need to modify them to have a queue parameter.

            :param args: Arguments tied to the function
            :type args: tuple
            :param kwargs: Named arguments tied to the function
            :type kwargs: dict
            """
            func = kwargs.pop("func")
            queue = kwargs.pop("queue")
            result = func(*args, **kwargs)
            queue.put(result)

        queue = multiprocessing.Queue()
        kwargs.update({"func": func, "queue": queue})
        process = Process(target=inner_wrapper, args=args, kwargs=kwargs)

        # Running the process as a daemon prevents it from hanging if a SIGINT
        # is raised, as all childs will be terminated with it.
        # https://docs.python.org/2.7/library/multiprocessing.html#multiprocessing.Process.daemon
        process.daemon = True
        try:
            process.start()
            process.join()

            if process.exception:
                raise process.exception

            if process.is_alive():
                # If the process is still alive for some reason, try to
                # terminate it.
                process.terminate()

            if not queue.empty():
                # We don't need to block the I/O as we are mostly done with
                # the child process and no exception was raised, so we can
                # instantly retrieve the item that was in the queue.
                return queue.get(block=False)

            return None
        except KeyboardInterrupt:
            # We have to check if the process if alive, and if it is (most
            # probably it will be), then we can call for termination. On
            # Python2 it is most likely that some processes (That calls yum
            # API) will keep executing until they finish their execution and
            # ignore the call for termination issued by the parent. To avoid
            # having "zombie" processes, we need to wait for them to finish.
            logger.warning("Terminating child process.")
            if process.is_alive():
                logger.debug("Process with pid %s is alive.", process.pid)
                process.terminate()

            logger.debug("Process with pid %s exited.", process.pid)

            # If there is a KeyboardInterrupt raised while the child process is
            # being executed, let's just re-raise it to the stack and move on.
            raise

    # Python2 and Python3 < 3.2 compatibility
    if not hasattr(wrapper, "__wrapped__"):
        wrapper.__wrapped__ = func

    return wrapper


def require_root():
    if os.geteuid() != 0:
        logger.critical("The tool needs to be run under the root user.\nNo changes were made to the system.")


def get_file_content(filename, as_list=False):
    """Return content of a file either as a list of lines or as a multiline
    string.
    """
    lines = []
    if not os.path.exists(filename):
        if not as_list:
            return ""
        return lines
    with open(filename, "r") as file_to_read:
        lines = file_to_read.readlines()
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

    with open(filename, "w") as handler:
        handler.write(content)


def restart_system():
    if tool_opts.restart:
        run_subprocess(["reboot"])
    else:
        logger.warning("In order to boot the RHEL kernel, restart of the system is needed.")


def run_subprocess(cmd, print_cmd=True, print_output=True):
    """Call the passed command and optionally log the called command (print_cmd=True) and its
    output (print_output=True). Switching off printing the command can be useful in case it contains
    a password in plain text.

    The cmd is specified as a list starting with the command and followed by a list of arguments.
    Example: ["dnf", "repoquery", "kernel"]
    """
    # This check is here because we passed in strings in the past and changed to a list
    # for security hardening.  Remove this once everyone is comfortable with using a list
    # instead.
    if isinstance(cmd, str):
        raise TypeError("cmd should be a list, not a str")

    if print_cmd:
        logger.debug("Calling command '{}'".format(" ".join(cmd)))

    process = subprocess.Popen(
        # Popen is only a context manager in Python-3.2+
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=-1,
    )
    output = ""
    for line in iter(process.stdout.readline, b""):
        line = line.decode("utf-8")
        output += line
        if print_output:
            logger.info(line.rstrip("\n"))

    # Call communicate() to wait for the process to terminate so that we can
    # get the return code.
    process.communicate()

    return output, process.returncode


def run_cmd_in_pty(cmd, expect_script=(), print_cmd=True, print_output=True, columns=150):
    """Similar to run_subprocess(), but the command is executed in a pseudo-terminal.

    The pseudo-terminal can be useful when a command prints out a different output with or without an active terminal
    session. E.g. yumdownloader does not print the name of the downloaded rpm if not executed from a terminal.
    Switching off printing the command can be useful in case it contains a password in plain text.

    :param cmd: The command to execute, including the options as a list, e.g. ["ls", "-al"]
    :type cmd: list
    :param expect_script: An iterable of pairs of expected strings and response strings. By giving
    these pairs, interactive programs can be scripted.  Example:
        run_cmd_in_pty(['sudo', 'whoami'], [('password: ', 'sudo_password\n')])
        Note1: The caller is responsible for adding newlines to the response strings where
        needed. Note2: This function will await pexpect.EOF after all of the pairs in expect_script
        have been exhausted.
    :type expect_script: iterable of 2-tuples or strings:
    :param print_cmd: Log the command (to both logfile and stdout)
    :type print_cmd: bool
    :param print_output: Log the combined stdout and stderr of the executed command (to both logfile and stdout)
    :type print_output: bool
    :param columns: Number of columns of the pseudo-terminal (characters on a line). This may influence the output.
    :type columns: int
    :return: The output (combined stdout and stderr) and the return code of the executed command
    :rtype: tuple

    .. warning:: unittests which utilize this may fail on pexpect-2.3 (RHEL7) unless capfd
        (pytest's capture of stdout) is disabled.  Look at the
        test_run_cmd_in_pty_size_set_on_startup unittest for an example.
    """
    # This check is here because we passed in strings in the past and changed to a list
    # for security hardening.  Remove this once everyone is comfortable with using a list
    # instead.
    if isinstance(cmd, str):
        raise TypeError("cmd should be a list, not a str")

    if print_cmd:
        logger.debug("Calling command '{}'".format(" ".join(cmd)))

    process = PexpectSpawnWithDimensions(
        cmd[0],
        cmd[1:],
        env={
            "LC_ALL": i18n.SCREENSCRAPED_LOCALE,
            "LANG": i18n.SCREENSCRAPED_LOCALE,
            "LANGUAGE": i18n.SCREENSCRAPED_LOCALE,
        },
        timeout=None,
        dimensions=(1, columns),
    )

    for expect, send in expect_script:
        process.expect(expect)
        process.send(send)

    process.expect(pexpect.EOF)
    try:
        process.wait()
    except pexpect.ExceptionPexpect:
        # RHEL 7's pexpect throws an exception if the process has already exited
        # We're just waiting to be sure that the process has finished so we can
        # ignore the exception.
        pass

    # Per the pexpect API, this is necessary in order to get the return code
    process.close()
    return_code = process.exitstatus

    output = process.before.decode()
    if print_output:
        logger.info(output.rstrip("\n"))

    return output, return_code


class PexpectSpawnWithDimensions(pexpect.spawn):
    """
    Pexpect.spawn class that can set terminal size before starting process.

    This class is a workaround to the fact that pexpect-2.3 cannot officially set the terminal size
    until after the process is started.  On RHEL7, we use pexpect 2.3 along with yumdownloader.
    yundownloader checks the terminal size when it starts and then uses that terminal size for
    printing out its progress lines even if the size changes later.  This causes output to be
    truncated (losing information about the downloaded packages) because the line would be longer
    than the 80 columns which pexpect.spawn hardcodes as the startup value.

    Modern versions of pexpect (from 2015) fix this by giving spawn a dimensions() argument to set
    the startup terminal size.  We can emulate this by overriding the setwindowsize() function in
    a subclass through the use of a big kludge:

    pexpect-2.3's __init__() calls setwindowsize() to set the initial terminal size. If we
    override setwindowsize() to hardcode the dimensions that we pass in to the subclass's
    constructor prior to calling the base class's __init__(), pexpect will end up calling our
    overridden setwindowsize(), making the terminal the size that we want. If we then revert
    setwindowsize() back to the real function prior to returning from the subclass's __init__(),
    user's of the returned spawn object won't know that we temporarily overrode that method.

    .. warning:: unittests which utilize this may fail on pexpect-2.3 (RHEL7) unless capfd
        (pytest's capture of stdout) is disabled.  Look at the
        test_run_cmd_in_pty_size_set_on_startup unittest for an example.
    """

    def __init__(self, *args, **kwargs):
        try:
            # With pexpect-2.4+, dimensions is a valid keyword arg
            super(PexpectSpawnWithDimensions, self).__init__(*args, **kwargs)
        except TypeError:
            #
            # This is a kludge to give us a dimensions kwarg on pexpect 2.3 or less.
            #
            if "dimensions" not in kwargs:
                # We can only handle the case where the exception is caused by passing dimensions
                # to pexpect.spawn.  If that's not what's happening here, re-raise the exception.
                raise

            dimensions = kwargs.pop("dimensions")

            # pexpect.spawn.__init__() calls setwinsize to set the rows and columns to a default
            # value.  Temporarily override setwinsize with a version that hardcodes the rows
            # and columns to set rows and columns before the process is spawned.
            # https://github.com/pexpect/pexpect/issues/134
            def _setwinsize(rows, cols):
                # This is a closure.  It takes self and dimensions from the function's defining scope.
                super(PexpectSpawnWithDimensions, self).setwinsize(dimensions[0], dimensions[1])

            # Save the real setwinsize and monkeypatch our kludge in
            real_setwinsize = self.setwinsize
            self.setwinsize = _setwinsize

            # Call pexpect.spawn.__init__() which will use the monkeypatched setwinsize()
            super(PexpectSpawnWithDimensions, self).__init__(*args, **kwargs)

            # Restore the real setwinsize
            self.setwinsize = real_setwinsize


def ask_to_continue():
    """Ask user whether to continue with the system conversion. If no,
    execution of the tool is stopped.
    """
    if tool_opts.autoaccept:
        return
    while True:
        cont = prompt_user("\nContinue with the system conversion? [y/n]: ")
        if cont == "y":
            break
        if cont == "n":
            logger.critical("User canceled the conversion.\n")


def prompt_user(question, password=False):
    """Prompt the user with a question and return his response to the caller.

    :param question: The question to prompt to the user.
    :param password: If the question is for a password, then the output is blanked out.

    This will return the user response to the caller as a string.
    """
    color_question = Color.BOLD + question + Color.END

    if password:
        response = getpass.getpass(color_question)
    else:
        response = moves.input(color_question)
    logger.info("\n")

    return response


def log_traceback(debug):
    """Log a traceback either to both a file and stdout, or just file, based
    on the debug parameter.
    """
    traceback_str = get_traceback_str()
    if debug:
        # Print the traceback to the user when debug option used
        logger.debug(traceback_str)
    else:
        # Print the traceback to the log file in any way
        logger.file(traceback_str)


def get_traceback_str():
    """Get a traceback of an exception as a string."""
    exc_type, exc_value, exc_traceback = sys.exc_info()
    return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))


def remove_tmp_dir():
    """Remove temporary folder (TMP_DIR), not needed post-conversion."""
    try:
        shutil.rmtree(TMP_DIR)
        logger.info("Temporary folder {} removed.".format(TMP_DIR))
    except OSError as err:
        logger.warning("Failed removing temporary folder {}\nError ({}): {}".format(TMP_DIR, err.errno, err.strerror))
    except TypeError:
        logger.warning("TypeError error while removing temporary folder {}.".format(TMP_DIR))


class DictWListValues(dict):
    """Python 2.4 replacement for Python 2.5+ collections.defaultdict(list)."""

    def __getitem__(self, item):
        if item not in iter(self.keys()):
            self[item] = []

        return super(DictWListValues, self).__getitem__(item)


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

    logger.debug("Downloading the {} package.".format(pkg))

    # On RHEL 7, it's necessary to invoke yumdownloader with -v, otherwise there's no output to stdout.
    cmd = ["yumdownloader", "-v", "--setopt=exclude=", "--destdir={}".format(dest)]
    if reposdir:
        cmd.append("--setopt=reposdir={}".format(reposdir))

    if isinstance(disable_repos, list):
        for repo in disable_repos:
            cmd.append("--disablerepo={}".format(repo))

    if isinstance(enable_repos, list):
        for repo in enable_repos:
            cmd.append("--enablerepo={}".format(repo))

    if set_releasever:
        if not custom_releasever and not system_info.releasever:
            raise AssertionError("custom_releasever or system_info.releasever must be set.")

        if custom_releasever:
            cmd.append("--releasever={}".format(custom_releasever))
        else:
            cmd.append("--releasever={}".format(system_info.releasever))

    if varsdir:
        cmd.append("--setopt=varsdir={}".format(varsdir))

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

    logger.info("Successfully downloaded the {} package.".format(pkg))
    logger.debug("Path of the downloaded package: {}".format(path))

    return path


def remove_pkgs(pkgs_to_remove, critical=True):
    """Remove packages not heeding to their dependencies.

    .. note::
        Following the work on https://github.com/oamg/convert2rhel/pull/1041,
        we might move this on it's own utils module.

    :param pkgs_to_remove list[str]: List of packages to remove.
    :param critical bool: If it should raise an exception in case of failure of
        removing a package.
    :returns list[str]: A list of packages removed. If no packages are provided
        to remove, an empty list will be returned.
    """
    pkgs_removed = []

    if not pkgs_to_remove:
        logger.info("No package to remove.")
        return pkgs_removed

    pkgs_failed_to_remove = []
    for nevra in pkgs_to_remove:
        # It's necessary to remove an epoch from the NEVRA string returned by yum because the rpm command does not
        # handle the epoch well and considers the package we want to remove as not installed. On the other hand, the
        # epoch in NEVRA returned by dnf is handled by rpm just fine.
        nvra = _remove_epoch_from_yum_nevra_notation(nevra)
        logger.info("Removing package: {}".format(nvra))
        _, ret_code = run_subprocess(["rpm", "-e", "--nodeps", nvra])
        if ret_code != 0:
            pkgs_failed_to_remove.append(nevra)
        else:
            pkgs_removed.append(nevra)

    if pkgs_failed_to_remove:
        pkgs_as_str = format_sequence_as_message(pkgs_failed_to_remove)
        if critical:
            logger.critical_no_exit("Error: Couldn't remove {}.".format(pkgs_as_str))
            raise exceptions.CriticalError(
                id_="FAILED_TO_REMOVE_PACKAGES",
                title="Couldn't remove packages",
                description="While attempting to roll back changes, we encountered an unexpected failure while attempting to remove one or more of the packages we installed earlier.",
                diagnosis="Couldn't remove {}.".format(pkgs_as_str),
            )
        else:
            logger.warning("Couldn't remove {}.".format(pkgs_as_str))

    return pkgs_removed


def _remove_epoch_from_yum_nevra_notation(package_nevra):
    """Remove epoch from the NEVRA string returned by yum.

    Yum prints epoch only when it's non-zero. It's printed differently by yum and dnf:
      yum - epoch before name: "7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      dnf - epoch before version: "oraclelinux-release-8:8.2-1.0.8.el8.x86_64"

    This function removes the epoch from the yum notation only.
    It's safe to pass the dnf notation string with an epoch. This function will return it as is.
    """
    epoch_match = re.search(r"^\d+:(.*)", package_nevra)
    if epoch_match:
        # Return NVRA without the found epoch
        return epoch_match.group(1)

    return package_nevra


def report_on_a_download_error(output, pkg):
    """
    Report on a failure to download a package we need for a complete rollback.

    :param output: Output of the yumdownloader call
    :param pkg: Name of a package to be downloaded
    """
    logger.warning("Output from the yumdownloader call:\n{}".format(output))

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
    from convert2rhel.systeminfo import system_info

    if tool_opts.activity == "conversion":
        warn_deprecated_env("CONVERT2RHEL_INCOMPLETE_ROLLBACK")
        if not tool_opts.incomplete_rollback:
            logger.critical(
                "Couldn't download the {} package. This means we will not be able to do a"
                " complete rollback and may put the system in a broken state.\n"
                "Check to make sure that the {} repositories are enabled"
                " and the package is updated to its latest version.\n"
                "If you would rather disregard this check set the incomplete_rollback option in the"
                " /etc/convert2rhel.ini config file to true.".format(pkg, system_info.name)
            )
        else:
            logger.warning(
                "Couldn't download the {} package. This means we will not be able to do a"
                " complete rollback and may put the system in a broken state.\n"
                "You have set the incomplete rollback inhibitor override, continuing"
                " conversion.".format(pkg)
            )
    else:
        logger.critical(
            "Couldn't download the {} package which is needed to do a rollback of this action."
            " Check to make sure that the {} repositories are enabled and the package is"
            " updated to its latest version.\n"
            "Note that you can choose to disregard this check when running a conversion by"
            " setting the incomplete_rollback option in the /etc/convert2rhel.ini config file to true,"
            " but not during a pre-conversion analysis.".format(pkg, system_info.name)
        )


def get_rpm_path_from_yumdownloader_output(cmd, output, dest):
    """Parse the output of yumdownloader to get the filepath of the downloaded rpm.

    The name of the downloaded rpm is in the output of a successful yumdownloader call. The output can look like:
      RHEL 7 & 8: "vim-enhanced-8.0.1763-13.0.1.el8.x86_64.rpm     2.2 MB/s | 1.4 MB     00:00"
      RHEL 7: "using local copy of 7:oraclelinux-release-7.9-1.0.9.el7.x86_64"
      RHEL 8: "[SKIPPED] oraclelinux-release-8.2-1.0.8.el8.x86_64.rpm: Already downloaded"
    """
    if not output:
        logger.warning("The output of running yumdownloader is unexpectedly empty. Command:\n{}".format(cmd))
        return None

    rpm_name_match = re.search(r"\S+\.rpm", output)
    pkg_nevra_match = re.search(r"using local copy of (?:\d+:)?(\S+)", output)

    if rpm_name_match:
        path = os.path.join(dest, rpm_name_match.group(0))
    elif pkg_nevra_match:
        path = os.path.join(dest, pkg_nevra_match.group(1) + ".rpm")
    else:
        logger.warning(
            "Couldn't find the name of the downloaded rpm in the output of yumdownloader.\n"
            "Command:\n{}\nOutput:\n{}".format(cmd, output)
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


def find_keyid(keyfile):
    """
    Find the keyid as used by rpm from a gpg key file.

    :arg keyfile: The filename that contains the gpg key.

    .. note:: rpm doesn't use the full gpg fingerprint so don't use that even though it would be
        more secure, instead use the key id.
    """
    # Newer gpg versions have several easier ways to do this:
    # gpg --with-colons --show-keys keyfile (Can pipe keyfile)
    # gpg --with-colons --import-options show-only --import keyfile  (Can pipe keyfile)
    # gpg --with-colons --import-options import-show --dry-run --import keyfile (Can pipe keyfile)
    # But as long as we need to work on RHEL7 we can't use those.

    # GPG needs a writable diretory to put default config files
    temporary_dir = tempfile.mkdtemp()
    temporary_keyring = os.path.join(temporary_dir, "keyring")

    try:
        # Step 1: Import the key into a temporary keyring (the list-keys command can't operate on
        # a single asciiarmored key)
        output, ret_code = run_subprocess(
            [
                "gpg",
                "--no-default-keyring",
                "--keyring",
                temporary_keyring,
                "--homedir",
                temporary_dir,
                "--import",
                keyfile,
            ],
            print_output=False,
        )
        if ret_code != 0:
            raise ImportGPGKeyError("Failed to import the rpm gpg key into a temporary keyring: {}".format(output))

        # Step 2: Print the information about the keys in the temporary keyfile.
        # --with-colons give us guaranteed machine parsable, stable output.
        output, ret_code = run_subprocess(
            [
                "gpg",
                "--no-default-keyring",
                "--keyring",
                temporary_keyring,
                "--homedir",
                temporary_dir,
                "--list-keys",
                "--with-colons",
            ],
            print_output=False,
        )
        if ret_code != 0:
            raise ImportGPGKeyError("Failed to read the temporary keyring with the rpm gpg key: {}".format(output))
    finally:
        # Try five times to work around a race condition:
        #
        # Gpg writes a temporary socket file for a gpg-agent into
        # --homedir.  Sometimes gpg removes that socket file after rmtree
        # has determined it should delete that file but before the deletion
        # occurs. This will cause a FileNotFoundError (OSError on Python
        # 2).  If we encounter that, try to run shutil.rmtree again since
        # we should now be able to remove all the files that were left.
        for _dummy in range(0, 5):
            try:
                # Remove the temporary keyring.  We can't use the context manager
                # for this because it isn't available on Python-2.7 (RHEL7)
                shutil.rmtree(temporary_dir)
            except OSError as e:
                # File not found means rmtree tried to remove a file that had
                # already been removed by the time it tried.
                if e.errno != 2:
                    raise
            else:
                break
        else:
            # If we get here, we tried and failed to rmtree five times
            # Don't make this fatal but do let the user know so they can clean
            # it up themselves.
            logger.info(
                "Failed to remove temporary directory {} that held Red Hat gpg public keys.".format(temporary_dir)
            )

    keyid = None
    for line in output.splitlines():
        if line.startswith("pub"):
            fields = line.split(":")
            key_id = fields[4]
            # The keyid as represented in rpm's fake packagename is only the last 8 hex digits
            # Example: gpg-pubkey-d651ff2e-5dadbbc1
            keyid = key_id[-8:]
            break

    if not keyid:
        raise ImportGPGKeyError("Unable to determine the gpg keyid for the rpm key file: {}".format(keyfile))

    return keyid.lower()


def remove_orphan_folders():
    """Even after removing redhat-release-* package, some of its folders are
    still present, are empty, and that blocks us from installing centos-release
    pkg back. So, for now, we are removing them manually.
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


def get_terminal_size():
    """Retrieve the terminal size on Linux systems"""
    try:
        # Python 3.2+
        return shutil.get_terminal_size()
    except AttributeError:
        pass

    # Retrieve the terminal size on Linux systems in Python2

    # We can't query the terminal size if it isn't a tty (For instance, if
    # output is piped.  Use a default value in that case)
    if not sys.stdout.isatty():
        return (80, 24)

    terminal_size_c_struct = struct.pack("HHHH", 0, 0, 0, 0)
    terminal_info = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, terminal_size_c_struct)

    size = struct.unpack("HHHH", terminal_info)[:2]
    # The fcntl data has height, width but shutil.get_terminal_size, which
    # we're emulating uses width, height.
    return (size[1], size[0])


def hide_secrets(
    args, secret_options=frozenset(("--username", "--password", "--activationkey", "--org", "-u", "-p", "-k", "-o"))
):
    """
    Replace secret values passed through a command line with asterisks.

    This function takes a list of command line arguments and returns a new list containing where any secret value is
    replaced with a fixed size of asterisks (*).

    Terminology:
     - an argument is one of whitespace delimited strings of an executed cli command
       Example: `ls -a -w 10 dir` ... four arguments (-a, -w, 10, dir)
     - an option is a subset of arguments that start with - or -- and modify the behavior of a cli command
       Example: `ls -a -w 10 dir` ... two options (-a, -w)
     - an option parameter is the argument following an option if the option requires a value
       Example: `ls -a -w 10 dir` ... one option parameter (10)

    :param: args: A list of command line arguments which may contain secret values.
    :param: secret_options: A set of command line options requiring sensitive or private information.
    :returns: A new list of arguments with secret values hidden.
    """
    sanitized_list = []
    hide_next = False
    for arg in args:
        if hide_next:
            # This is a parameter of a secret option
            arg = OBFUSCATION_STRING
            hide_next = False

        elif arg in secret_options:
            # This is a secret option => mark its parameter (the following argument) to be obfuscated
            hide_next = True

        else:
            # Handle the case where the secret option and its parameter are both in one argument ("--password=SECRET")
            for option in secret_options:
                if arg.startswith(option + "="):
                    arg = "{0}={1}".format(option, OBFUSCATION_STRING)

        sanitized_list.append(arg)

    if hide_next:
        logger.debug(
            "Passed arguments had an option, '{0}', without an expected secret parameter".format(sanitized_list[-1])
        )

    return sanitized_list


def format_sequence_as_message(sequence_of_items):
    """
    Format a sequence of items for display to the user.

    :param sequence_of_items: Sequence of items which should be formatted for
        a message to be printed to the user.
    :type sequence_of_items: Sequence
    :returns: Items formatted appropriately for end user output.
    :rtype: str
    """
    if len(sequence_of_items) < 1:
        message = ""
    elif len(sequence_of_items) == 1:
        message = sequence_of_items[0]
    elif len(sequence_of_items) == 2:
        message = " and ".join(sequence_of_items)
    else:
        message = ", ".join(sequence_of_items[:-1]) + ", and " + sequence_of_items[-1]

    return message


def flatten(dictionary, parent_key=False, separator="."):
    """Turn a nested dictionary into a flattened dictionary.

    .. note::
        If we detect a empty dictionary or list, this function will append a "null" as a value to the key.

    :param dictionary: The dictionary to flatten
    :param parent_key: The string to prepend to dictionary's keys
    :param separator: The string used to separate flattened keys
    :return: A flattened dictionary
    """

    items = []
    for key, value in dictionary.items():
        new_key = str(parent_key) + separator + key if parent_key else key

        if isinstance(value, dict):
            if not value:
                items.append((new_key, "null"))
            else:
                items.extend(flatten(value, new_key, separator).items())
        elif isinstance(value, list):
            if not value:
                items.append((new_key, "null"))
            else:
                for k, v in enumerate(value):
                    items.extend(flatten({str(k): v}, new_key).items())
        else:
            items.append((new_key, value))
    return dict(items)


def write_json_object_to_file(path, data, mode=0o600):
    """Write a Json object to a file in the system.

    :param path: The path of the file to be written.
    :type path: str
    :param data: The JSON data that will be written.
    :type data: dict[str, Any]
    :param mode: The permissions for the file.
    :type mode: int
    """
    with open(path, mode="w") as handler:
        os.chmod(path, mode)
        json.dump(data, handler, indent=4)


def warn_deprecated_env(env_name):
    """Warn the user that the environment variable is deprecated.

    .. note::
        This will be removed after we finalize switching all env vars to toolopts.

    :param env_name: The name of the environment variable that is deprecated.
    :type env_name: str
    """
    env_var_to_toolopts_map = {
        "CONVERT2RHEL_OUTDATED_PACKAGE_CHECK_SKIP": "outdated_package_check_skip",
        "CONVERT2RHEL_SKIP_KERNEL_CURRENCY_CHECK": "skip_kernel_currency_check",
        "CONVERT2RHEL_INCOMPLETE_ROLLBACK": "incomplete_rollback",
        "CONVERT2RHEL_ALLOW_UNAVAILABLE_KMODS": "allow_unavailable_kmods",
        "CONVERT2RHEL_ALLOW_OLDER_VERSION": "allow_older_version",
        "CONVERT2RHEL_CONFIGURE_HOST_METERING": "configure_host_metering",
        "CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP": "tainted_kernel_module_check_skip",
    }

    if env_name not in os.environ:
        # Nothing to do here.
        return None

    root_logger.warning(
        "The environment variable {} is deprecated and will be removed in convert2rhel 2.4.0.\n"
        "Use the {} option in the /etc/convert2rhel.ini configuration file.".format(
            env_name, env_var_to_toolopts_map[env_name]
        )
    )
    key = env_var_to_toolopts_map[env_name]
    value = os.getenv(env_name, None)
    tool_opts.update_opts(key, value)
