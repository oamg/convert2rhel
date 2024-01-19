__metaclass__ = type

import fcntl
import getpass
import inspect
import logging
import os
import shutil
import struct
import subprocess
import sys
import termios

import pexpect

from six import moves

from convert2rhel import i18n


loggerinst = logging.getLogger(__name__)


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


def get_executable_name():
    """Get name of the executable file passed to the python interpreter."""

    return os.path.basename(inspect.stack()[-1][1])


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
        loggerinst.debug("Calling command '%s'" % " ".join(cmd))

    process = subprocess.Popen(  # pylint: disable=consider-using-with
        # Popen is only a context manager in Python-3.2+
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    output = ""
    for line in iter(process.stdout.readline, b""):
        line = line.decode("utf8")
        output += line
        if print_output:
            loggerinst.info(line.rstrip("\n"))

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
        loggerinst.debug("Calling command '%s'" % " ".join(cmd))

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
        loggerinst.info(output.rstrip("\n"))

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
            real_setwinsize = self.setwinsize  # pylint: disable=access-member-before-definition
            self.setwinsize = _setwinsize

            # Call pexpect.spawn.__init__() which will use the monkeypatched setwinsize()
            super(PexpectSpawnWithDimensions, self).__init__(*args, **kwargs)

            # Restore the real setwinsize
            self.setwinsize = real_setwinsize


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
    loggerinst.info("\n")

    return response
