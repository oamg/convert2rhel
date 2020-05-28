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

from datetime import datetime

import logging
import os
import shutil

try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

from convert2rhel import logger
from convert2rhel import unit_tests  # Imports unit_tests/__init__.py
from convert2rhel.toolopts import tool_opts


class TestLogger(unittest.TestCase):

    @unit_tests.mock(logger, "LOG_DIR", unit_tests.TMP_DIR)
    def setUp(self):
        # initialize class variables
        self.log_dir = logger.LOG_DIR
        self.log_file = "convert2rhel.log"
        self.test_msg = "testmsg"

        # remove the directory to ensure the content is clean
        if os.path.exists(logger.LOG_DIR):
            shutil.rmtree(logger.LOG_DIR)
        # initialize logger
        logger.initialize_logger(self.log_file)

    def test_set_logger(self):
        loggerinst = logging.getLogger("convert2rhel.unittests")
        handlers = loggerinst.handlers

        # find parent logger instances where our handlers exist
        while len(handlers) == 0:
            loggerinst = loggerinst.parent
            handlers = loggerinst.handlers

        # verify both StreamHandler and FileHandler have been created
        has_stream_handler_instance = False
        has_file_handler_instance = False
        for handler in handlers:
            if isinstance(handler, logging.StreamHandler):
                has_stream_handler_instance = True
            if isinstance(handler, logging.FileHandler):
                has_file_handler_instance = True

        self.assertTrue(has_stream_handler_instance)
        self.assertTrue(has_file_handler_instance)

        # verify log file name
        for handler in handlers:
            if type(handler) is logging.FileHandler:
                log_path = os.path.join(self.log_dir, self.log_file)
                self.assertEqual(log_path, handler.baseFilename)

    def test_log_format(self):
        self.dummy_handler = logging.StreamHandler()

        custom_formatter = logger.CustomFormatter("%(message)s")

        self.dummy_handler.setFormatter(custom_formatter)
        dt_strformat = '[%m/%d/%Y %H:%M:%S] DEBUG - '
        tempstr = datetime.now().strftime(dt_strformat) + self.test_msg
        self.check_formatter_result(
            logging.DEBUG, tempstr)
        self.check_formatter_result(
            logging.INFO, self.test_msg)
        tempstr = "WARNING - %s" % self.test_msg
        self.check_formatter_result(
            logging.WARNING, tempstr)

    def check_formatter_result(self, log_level, expected_result):
        rec = logging.LogRecord("", log_level, "", 0, self.test_msg, (), None)
        formatted_msg = self.dummy_handler.format(rec)
        self.assertEqual(formatted_msg, expected_result)

    class HandlerHandleMocked(unit_tests.MockFunction):
        def __init__(self):
            self.called = 0

        def __call__(self, rec):
            self.called += 1

    @unit_tests.mock(logging.Handler, "handle", HandlerHandleMocked())
    def test_log_to_file(self):
        loggerinst = logging.getLogger(__name__)
        loggerinst.file(self.test_msg)

        # Handler is a base class for all log handlers (incl. FileHandler)
        self.assertEqual(logging.Handler.handle.called, 1)

    @unit_tests.mock(logging.Handler, "handle", HandlerHandleMocked())
    @unit_tests.mock(tool_opts, "debug", True)
    def test_log(self):
        loggerinst = logging.getLogger(__name__)
        loggerinst.debug("debugmsg1")
        loggerinst.info("infomsg")
        loggerinst.warning("warningmsg")

        # generic handler called (2 handlers called for each function above)
        # except debug level which is logged only with --debug option
        self.assertEqual(logging.Handler.handle.called, 6)
        tool_opts.debug = False
        loggerinst.debug("debugmsg2")
        self.assertEqual(logging.Handler.handle.called, 7)
