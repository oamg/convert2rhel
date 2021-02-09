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

import logging
import os

import pytest

from convert2rhel import logger as logger_module
from convert2rhel.logger import CustomLogger
from convert2rhel.toolopts import tool_opts


def test_logger_handlers(tmpdir, caplog, read_std, is_py2, capsys):
    """Test if the logger handlers emmits the events to the file and stdout."""
    # initializing the logger first
    log_fname = "convert2rhel.log"
    tool_opts.debug = True  # debug entries > stdout if True
    logger_module.initialize_logger(log_name=log_fname, log_dir=tmpdir)
    logger = logging.getLogger(__name__)

    # emitting some log entries
    logger.info("Test info")
    logger.debug("Test debug")

    # Test if logs were emmited to the file
    with open(os.path.join(tmpdir, log_fname)) as log_f:
        assert "Test info" in log_f.readline().rstrip()
        assert "Test debug" in log_f.readline().rstrip()

    # Test if logs were emmited to the stdout
    stdouterr_out, stdouterr_err = read_std()
    assert "Test info" in stdouterr_out
    assert "Test debug" in stdouterr_out


def test_tools_opts_debug(tmpdir, read_std, is_py2):
    log_fname = "convert2rhel.log"
    logger_module.initialize_logger(log_name=log_fname, log_dir=tmpdir)
    logger = logging.getLogger(__name__)
    tool_opts.debug = True
    logger.debug("debug entry 1")
    stdouterr_out, stdouterr_err = read_std()
    # TODO should be in stdout, but this only works when running this test
    #   alone (see https://github.com/pytest-dev/pytest/issues/5502)
    try:
        assert "debug entry 1" in stdouterr_out
    except AssertionError:
        if not is_py2:
            assert "debug entry 1" in stdouterr_err
        else:
            # this workaround is not working for py2 - passing
            pass
    tool_opts.debug = False
    logger.debug("debug entry 2")
    stdouterr_out, stdouterr_err = read_std()
    assert "debug entry 2" not in stdouterr_out


def test_logger_custom_logger(tmpdir, caplog):
    """Test CustomLogger."""
    log_fname = "convert2rhel.log"
    logger_module.initialize_logger(log_name=log_fname, log_dir=tmpdir)
    logger = logging.getLogger(__name__)
    assert isinstance(logger, CustomLogger)
    logger.task("Some task")
    logger.file("Some task write to file")
    with pytest.raises(SystemExit):
        logger.critical("Critical error")
