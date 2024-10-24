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
import os
import shutil
import sys

from logging.handlers import BufferingHandler
from time import gmtime, strftime

from convert2rhel.phase import ConversionPhases

"""
Customized logging functionality

CRITICAL_NO_EXIT    (50)    Calls critical() function
CRITICAL            (50)    Calls critical() function and sys.exit(1)
ERROR               (40)    Prints error message using date/time
WARNING             (30)    Prints warning message using date/time
INFO                (20)    Prints info message (no date/time, just plain message)
TASK                (20)    CUSTOM LABEL - Prints a task header message (using asterisks)
DEBUG               (10)    Prints debug message (using date/time)
FILE                (10)    CUSTOM LABEL - Outputs with the DEBUG label but only to a file
"""


LOG_DIR = "/var/log/convert2rhel"


class LogLevelFile:
    level = 5
    # Label messages DEBUG as it is contains the same messages as debug, just that they always go
    # to the log file.
    label = "DEBUG"


class LogfileBufferHandler(BufferingHandler):
    """
    FileHandler we use in Convert2RHEL requries root due to the location and the
    tool itself checking for root user explicitly. Since we cannot obviously
    use the logger if we aren't root in that case we simply add the FileHandler
    after determining we're root.

    Caveat of that approach is that any logging prior to the initialization of
    the FileHandler would be lost, to help with this we have this custom handler
    which will keep a buffer of the logs and flush it to the FileHandler
    """

    def __init__(self, capacity, handler_name="file_handler"):
        """
        Initialize the handler with the buffer size.

        :param int capacity: Buffer size for the handler
        :param str handler_name: Handler to flush buffer to, defaults to "file_handler"
        """
        super(LogfileBufferHandler, self).__init__(capacity)
        # the FileLogger handler that we are logging to
        self._handler_name = handler_name
        self.set_name("logfile_buffer_handler")

    @property
    def target(self):
        """The computed Filehandler target that we are supposed to send to.

        This is mostly copied over from logging's MemoryHandler but instead of setting
        the target manually we find it automatically given the name of the handler

        :return logging.Handler: Either the found FileHandler setup or temporary NullHandler
        """
        for handler in root_logger.handlers:
            if hasattr(handler, "name") and handler.name == self._handler_name:
                return handler
        return logging.NullHandler()

    def flush(self):
        for record in self.buffer:
            self.target.handle(record)

    def shouldFlush(self, record):
        """
        We should never flush automatically, so we set this to always return false, that way we need to flush manually each time. Which is exactly what we want when it comes to keeping a buffer before we confirm we are
        a root user.

        :param logging.LogRecord record: The record to log
        :return bool: Always returns false
        """
        if super(LogfileBufferHandler, self).shouldFlush(record):
            self.buffer = self.buffer[1:]
        return False


def setup_logger_handler():
    """Setup custom logging levels, handlers, and so on. Call this method
    from your application's main start point.
    """
    # set custom labels
    logging.addLevelName(LogLevelFile.level, LogLevelFile.label)
    logging.Logger.debug = _debug
    logging.Logger.critical = _critical

    # enable raising exceptions
    logging.raiseExceptions = True
    # propagate
    root_logger.propagate = True
    # set default logging level
    root_logger.setLevel(LogLevelFile.level)

    # create sys.stdout handler for info/debug
    stdout_handler = logging.StreamHandler(sys.stdout)
    formatter = CustomFormatter("%(message)s")
    formatter.disable_colors(should_disable_color_output())
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(stdout_handler)

    # can flush logs to the file that were logged before initializing the file handler
    root_logger.addHandler(LogfileBufferHandler(capacity=100))


def add_file_handler(log_name, log_dir):
    """Create a file handler for the logger instance

    :param str log_name: Name of the log file
    :param str log_dir: Full path location
    """
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)  # pragma: no cover
    filehandler = logging.FileHandler(os.path.join(log_dir, log_name), "a")
    filehandler.name = "file_handler"
    formatter = CustomFormatter("%(message)s")

    # With a file we don't really need colors
    # This might change in the future depending on customer requests
    # or if we do something with UI work in the future that would be more
    # helpful with colors
    formatter.disable_colors(True)
    filehandler.setFormatter(formatter)
    filehandler.setLevel(LogLevelFile.level)
    root_logger.addHandler(filehandler)

    # We now have a FileHandler added, but we still need the logs from before
    # this point. Luckily we have the memory buffer that we can flush logs from
    for handler in root_logger.handlers:
        if hasattr(handler, "name") and handler.name == "logfile_buffer_handler":
            handler.close()
            # after we've flushed to the file we don't need the handler anymore
            root_logger.removeHandler(handler)
            break


def should_disable_color_output():
    """
    Return whether NO_COLOR exists in environment parameter and is true.

    See https://no-color.org/
    """
    if "NO_COLOR" in os.environ:
        NO_COLOR = os.environ["NO_COLOR"]
        return NO_COLOR is not None and NO_COLOR != "0" and NO_COLOR.lower() != "false"

    return False


def archive_old_logger_files(log_name, log_dir):
    """Archive the old log files to not mess with multiple runs outputs.
    Every time a new run begins, this method will be called to archive the previous logs
    if there is a `convert2rhel.log` file there, it will be archived using
    the same name for the log file, but having an appended timestamp to it.
        log_name = the name for the log file
        log_dir = path to the dir where log file will be presented

    For example:
        /var/log/convert2rhel/archive/convert2rhel-1635162445070567607.log
        /var/log/convert2rhel/archive/convert2rhel-1635162478219820043.log

    This way, the user can track the logs for each run individually based on the timestamp.
    """

    current_log_file = os.path.join(log_dir, log_name)
    archive_log_dir = os.path.join(log_dir, "archive")

    if not os.path.exists(current_log_file):
        # No log file found, that means it's a first run or it was manually deleted
        return

    stat = os.stat(current_log_file)

    # Get the last modified time in UTC
    last_modified_at = gmtime(stat.st_mtime)

    # Format time to a human-readable format
    formatted_time = strftime("%Y%m%dT%H%M%SZ", last_modified_at)

    # Create the directory if it don't exist
    if not os.path.exists(archive_log_dir):
        os.makedirs(archive_log_dir)

    file_name, suffix = tuple(log_name.rsplit(".", 1))
    archive_log_file = "{}/{}-{}.{}".format(archive_log_dir, file_name, formatted_time, suffix)
    shutil.move(current_log_file, archive_log_file)


def _critical(self, msg, *args, **kwargs):
    if self.isEnabledFor(logging.CRITICAL):
        self._log(logging.CRITICAL, msg, args, **kwargs)
        extra = kwargs.pop("extra", {})
        if not extra.get("no_exit"):
            sys.exit(msg)


def _debug(self, msg, *args, **kwargs):
    if self.isEnabledFor(logging.DEBUG):
        self._log(logging.DEBUG, msg, args, **kwargs)


class bcolors:
    OKGREEN = "\033[92m"
    INFO = "\033[94m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"


def colorize(message, color="OKGREEN"):
    """
    Add ANSI color escapes around a message.

    :param message: The message to add ANSI color escapes to.
    :type message: str
    :keyword color: The "color" to make the message.  Colors are taken from
        :class:`bcolors`. default: "OKGREEN"
    :type color: str
    :returns: String that contains the message encased in the ANSI escape
        sequence for `color`
    :rtype: str
    """
    return "".join((getattr(bcolors, color), message, bcolors.ENDC))


class CustomFormatter(logging.Formatter):
    """
    Custom formatter to handle different logging formats based on logging level.
    """

    color_disabled = False

    def disable_colors(self, value):
        self.color_disabled = value

    def format(self, record):
        """Format tasks, etc

        :param logging.LogRecord record: Logger-provided LogRecord that is
        provided when we use logging.warning() etc.
        :return str: The formatted log message
        """
        fmt_orig = "[%(asctime)s] %(levelname)s - %(message)s"  # DEBUG default
        self.datefmt = "%Y-%m-%dT%H:%M:%S%z"  # DEBUG default

        # Used when providing is_task in the extra field
        # e.g. logging.warning("Testing", extra={"is_task": True})
        is_task = getattr(record, "is_task", False)

        color = self._getLogLevelColor(record, is_task)
        if is_task:
            log_phase_name = ""
            if ConversionPhases.current_phase and ConversionPhases.current_phase.log_name:
                log_phase_name = "{}: ".format(ConversionPhases.current_phase.log_name)
            asterisks = "*" * (90 - len(log_phase_name) - len(record.msg) - 25)

            fmt_orig = "\n[%(asctime)s] TASK - [{log_phase_name}%(message)s] {asterisks}".format(
                log_phase_name=log_phase_name, asterisks=asterisks
            )

            self.datefmt = "%Y-%m-%dT%H:%M:%S%z"
        elif record.levelno >= logging.WARNING:
            fmt_orig = "%(levelname)s - %(message)s"
        elif record.levelno >= logging.INFO:
            fmt_orig = "%(message)s"
            self.datefmt = ""

        # apply colors to log if set
        new_fmt = fmt_orig
        if color and not self.color_disabled:
            new_fmt = colorize(fmt_orig, color)

        self._fmt = new_fmt
        if hasattr(self, "_style"):
            # Python 3 has _style for formatter
            # Overwriting the style _fmt gets the result we want
            self._style._fmt = self._fmt

        return super(CustomFormatter, self).format(record)

    def _getLogLevelColor(self, record, is_task=False):
        if is_task:
            return "OKGREEN"
        elif record.levelno >= logging.WARNING:
            return "WARNING"
        elif record.levelno >= logging.ERROR:
            return "FAIL"
        return None


class CustomLogger(logging.Logger):
    """Logger with extra features to cover Convert2RHEL usage.

    Without this we lack the code-completion and hinting necessary when defining custom messages.

    Within the codebase we want to log for different scenarios and to improve backwards compatibility.
    We have a custom task function for logging all the different steps we have within the codebase
    and it helps the user to differenciate between normal logs and different steps within the execution.

    critical_no_exit custom function is for when we want to raise a critical exception without throwing
    a SystemExit. This is here for backwards compatibility and will eventually be replaced by critical
    as we do not want critical function to exit.

    file is deprecated and will be removed.
    """

    def __init__(self, name, level=0):
        super(CustomLogger, self).__init__(name, level)

    def critical_no_exit(self, message, *args, **kwargs):
        return self.critical(message, extra={"no_exit": True}, *args, **kwargs)

    def task(self, message, *args, **kwargs):
        return self.info(message, extra={"is_task": True}, *args, **kwargs)

    def file(self, message, *args, **kwargs):
        return self.debug(message, *args, **kwargs)


# get root logger
logging.setLoggerClass(CustomLogger)
root_logger = logging.getLogger("convert2rhel")  # type: CustomLogger # type: ignore
