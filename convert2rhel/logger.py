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

"""
Customized logging functionality

CRITICAL_NO_EXIT    (50)    Calls critical() function
CRITICAL            (50)    Calls critical() function and sys.exit(1)
ERROR               (40)    Prints error message using date/time
WARNING             (30)    Prints warning message using date/time
INFO                (20)    Prints info message (no date/time, just plain message)
TASK                (15)    CUSTOM LABEL - Prints a task header message (using asterisks)
DEBUG               (10)    Prints debug message (using date/time)
FILE                (5)     CUSTOM LABEL - Outputs with the DEBUG label but only to a file
"""

import logging
import os
import shutil
import sys

from logging.handlers import BufferingHandler
from time import gmtime, strftime


LOG_DIR = "/var/log/convert2rhel"

# get root logger
logger = logging.getLogger("convert2rhel")


class LogLevelCriticalNoExit:
    level = 50
    label = "CRITICAL"


class LogLevelTask:
    level = 15
    label = "TASK"


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

    name = "logfile_buffer_handler"

    def __init__(self, capacity, handler_name="file_handler"):
        """_summary_

        :param int capacity: Initialize with a buffer size
        :param str handler_name: Handler to flush buffer to, defaults to "file_handler"
        """
        super(LogfileBufferHandler, self).__init__(capacity)
        # the FileLogger handler that we are logging to
        self._handler_name = handler_name

    @property
    def target(self):
        """The computed Filehandler target that we are supposed to send to. This
        is mostly copied over from logging's MemoryHandler but instead of setting
        the target manually we find it automatically given the name of the handler

        :return logging.Handler: Either the found FileHandler setup or temporary NullHandler
        """
        for handler in logger.handlers:
            if handler.name == self._handler_name:
                return handler
        return logging.NullHandler()

    def flush(self):
        for record in self.buffer:
            self.target.handle(record)

    def shouldFlush(self, record):
        """We should never flush automatically, so we set this to always return false, that way we need to flush
        manually each time. Which is exactly what we want when it comes to keeping a buffer before we confirm we are
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
    logging.addLevelName(LogLevelTask.level, LogLevelTask.label)
    logging.addLevelName(LogLevelFile.level, LogLevelFile.label)
    logging.addLevelName(LogLevelCriticalNoExit.level, LogLevelCriticalNoExit.label)
    logging.Logger.task = _task
    logging.Logger.file = _file
    logging.Logger.debug = _debug
    logging.Logger.critical = _critical
    logging.Logger.critical_no_exit = _critical_no_exit

    # enable raising exceptions
    logging.raiseExceptions = True
    # propagate
    logger.propagate = True
    # set default logging level
    logger.setLevel(LogLevelFile.level)

    # create sys.stdout handler for info/debug
    stdout_handler = logging.StreamHandler(sys.stdout)
    formatter = CustomFormatter("%(message)s")
    formatter.disable_colors(should_disable_color_output())
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(logging.DEBUG)
    logger.addHandler(stdout_handler)

    # Setup a buffer for the file handler that we will add later, that way we
    # can flush logs to the file that were logged before initializing the file handler
    logger.addHandler(LogfileBufferHandler(100))


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
    logger.addHandler(filehandler)

    # We now have a FileHandler added, but we still need the logs from before
    # this point. Luckily we have the memory buffer that we can flush logs from
    for handler in logger.handlers:
        if handler.name == "logfile_buffer_handler":
            handler.flush()
            # after we've flushed to the file we don't need the handler anymore
            logger.removeHandler(handler)
            break


def should_disable_color_output():
    """
    Return whether NO_COLOR exists in environment parameter and is true.

    See https://no-color.org/
    """
    if "NO_COLOR" in os.environ:
        NO_COLOR = os.environ["NO_COLOR"]
        return NO_COLOR != None and NO_COLOR != "0" and NO_COLOR.lower() != "false"

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
    archive_log_file = "%s/%s-%s.%s" % (archive_log_dir, file_name, formatted_time, suffix)
    shutil.move(current_log_file, archive_log_file)


def _task(self, msg, *args, **kwargs):
    if self.isEnabledFor(LogLevelTask.level):
        self._log(LogLevelTask.level, msg, args, **kwargs)


def _file(self, msg, *args, **kwargs):
    if self.isEnabledFor(LogLevelFile.level):
        self._log(LogLevelFile.level, msg, args, **kwargs)


def _critical(self, msg, *args, **kwargs):
    if self.isEnabledFor(logging.CRITICAL):
        self._log(logging.CRITICAL, msg, args, **kwargs)
        sys.exit(msg)


def _critical_no_exit(self, msg, *args, **kwargs):
    if self.isEnabledFor(LogLevelCriticalNoExit.level):
        self._log(LogLevelCriticalNoExit.level, msg, args, **kwargs)


def _debug(self, msg, *args, **kwargs):
    if self.isEnabledFor(logging.DEBUG):
        from convert2rhel.toolopts import tool_opts

        if tool_opts.debug:
            self._log(logging.DEBUG, msg, args, **kwargs)
        else:
            self._log(LogLevelFile.level, msg, args, **kwargs)


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
        if record.levelno == LogLevelTask.level:
            temp = "*" * (90 - len(record.msg) - 25)
            fmt_orig = "\n[%(asctime)s] %(levelname)s - [%(message)s] " + temp
            new_fmt = fmt_orig if self.color_disabled else colorize(fmt_orig, "OKGREEN")
            self._fmt = new_fmt
            self.datefmt = "%Y-%m-%dT%H:%M:%S%z"
        elif record.levelno in [logging.INFO]:
            self._fmt = "%(message)s"
            self.datefmt = ""
        elif record.levelno in [logging.WARNING]:
            fmt_orig = "%(levelname)s - %(message)s"
            new_fmt = fmt_orig if self.color_disabled else colorize(fmt_orig, "WARNING")
            self._fmt = new_fmt
            self.datefmt = ""
        elif record.levelno >= logging.ERROR:
            # Error, Critical, Critical_no_exit
            fmt_orig = "%(levelname)s - %(message)s"
            new_fmt = fmt_orig if self.color_disabled else colorize(fmt_orig, "FAIL")
            self._fmt = new_fmt
            self.datefmt = ""
        else:
            self._fmt = "[%(asctime)s] %(levelname)s - %(message)s"
            self.datefmt = "%Y-%m-%dT%H:%M:%S%z"

        if hasattr(self, "_style"):
            # Python 3 has _style for formatter
            # Overwriting the style _fmt gets the result we want
            self._style._fmt = self._fmt

        return super(CustomFormatter, self).format(record)
