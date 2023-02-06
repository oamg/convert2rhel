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
"""
Customized logging functionality

CRITICAL  (50)    Calls critical() function and sys.exit(1)
ERROR     (40)    Prints error message using date/time
WARNING   (30)    Prints warning message using date/time
INFO      (20)    Prints info message (no date/time, just plain message)
TASK      (15)    CUSTOM LABEL - Prints a task header message (using asterisks)
DEBUG     (10)    Prints debug message (using date/time)
FILE      (5)     CUSTOM LABEL - Outputs with the DEBUG label but only to a file
                  handle (using date/time)
"""

__metaclass__ = type

import logging
import os
import shutil
import sys

from time import gmtime, strftime


LOG_DIR = "/var/log/convert2rhel"


class LogLevelTask:
    level = 15
    label = "TASK"


class LogLevelFile:
    level = 5
    # Label messages DEBUG as it is contains the same messages as debug, just that they always go
    # to the log file.
    label = "DEBUG"


def setup_logger_handler(log_name, log_dir):
    """Setup custom logging levels, handlers, and so on. Call this method
    from your application's main start point.
        log_name = the name for the log file
        log_dir = path to the dir where log file will be presented
    """
    # set custom labels
    logging.addLevelName(LogLevelTask.level, LogLevelTask.label)
    logging.addLevelName(LogLevelFile.level, LogLevelFile.label)
    logging.Logger.task = _task
    logging.Logger.file = _file
    logging.Logger.debug = _debug
    logging.Logger.critical = _critical

    # enable raising exceptions
    logging.raiseExceptions = True
    # get root logger
    logger = logging.getLogger("convert2rhel")
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

    # create file handler
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)  # pragma: no cover
    handler = logging.FileHandler(os.path.join(log_dir, log_name), "a")
    formatter = CustomFormatter("%(message)s")
    formatter.disable_colors(True)
    handler.setFormatter(formatter)
    handler.setLevel(LogLevelFile.level)
    logger.addHandler(handler)


def should_disable_color_output():
    """
    Return whether NO_COLOR exists in environment parameter and is true.

    See http://no-color.org/
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
        elif record.levelno in [logging.CRITICAL, logging.ERROR]:
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
