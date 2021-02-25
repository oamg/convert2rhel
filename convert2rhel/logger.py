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
FILE      (5)     CUSTOM LABEL - Prints only to file handler (using date/time)
"""
import logging
import os
import sys

from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import format_msg_with_datetime

LOG_DIR = "/var/log/convert2rhel"


class LogLevelTask(object):
    level = 15
    label = "TASK"


class LogLevelFile(object):
    level = 5
    label = "FILE"


def initialize_logger(log_name, log_dir=LOG_DIR):
    """Initialize custom logging levels, handlers, and so on. Call this method
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
    formatter.disable_colors(tool_opts.disable_colors)
    stdout_handler.setFormatter(formatter)
    stdout_handler.setLevel(logging.DEBUG)
    logger.addHandler(stdout_handler)

    # create file handler
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)    # pragma: no cover
    handler = logging.FileHandler(os.path.join(log_dir, log_name), "a")
    formatter = CustomFormatter("%(message)s")
    formatter.disable_colors(True)
    handler.setFormatter(formatter)
    handler.setLevel(LogLevelFile.level)
    logger.addHandler(handler)


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
            self._log(
                LogLevelFile.level,
                format_msg_with_datetime(msg, "debug"),
                args,
                **kwargs
            )


class bcolors:
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


class CustomFormatter(logging.Formatter, object):
    """Custom formatter to handle different logging formats based on logging level

    Python 2.6 workaround - logging.Formatter class does not use new-style
        class and causes 'TypeError: super() argument 1 must be type, not
        classobj' so we use multiple inheritance to get around the problem.
    """
    color_disabled = False

    def disable_colors(self, value):
        self.color_disabled = value

    def format(self, record):
        if record.levelno == LogLevelTask.level:
            temp = '*' * (90 - len(record.msg) - 25)
            fmt_orig = "\n[%(asctime)s] %(levelname)s - [%(message)s] " + temp
            new_fmt = fmt_orig if self.color_disabled else bcolors.OKGREEN + fmt_orig + bcolors.ENDC
            self._fmt = new_fmt
            self.datefmt = "%m/%d/%Y %H:%M:%S"
        elif record.levelno in [logging.INFO, LogLevelFile.level]:
            self._fmt = "%(message)s"
            self.datefmt = ""
        elif record.levelno in [logging.WARNING]:
            fmt_orig = "%(levelname)s - %(message)s"
            new_fmt = fmt_orig if self.color_disabled else bcolors.WARNING + fmt_orig + bcolors.ENDC
            self._fmt = new_fmt
            self.datefmt = ""
        elif record.levelno in [logging.CRITICAL]:
            fmt_orig = "%(levelname)s - %(message)s"
            new_fmt = fmt_orig if self.color_disabled else bcolors.FAIL + fmt_orig + bcolors.ENDC
            self._fmt = new_fmt
            self.datefmt = ""
        else:
            self._fmt = "[%(asctime)s] %(levelname)s - %(message)s"
            self.datefmt = "%m/%d/%Y %H:%M:%S"

        if hasattr(self, '_style'):
            # Python 3 has _style for formatter
            # Overwriting the style _fmt gets the result we want
            self._style._fmt = self._fmt

        return super(CustomFormatter, self).format(record)
