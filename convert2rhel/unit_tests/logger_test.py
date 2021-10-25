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
from convert2rhel.toolopts import tool_opts


def test_logger_handlers(tmpdir, caplog, read_std, is_py2, capsys):
    """Test if the logger handlers emmits the events to the file and stdout."""
    # initializing the logger first
    log_fname = "convert2rhel.log"
    tool_opts.debug = True  # debug entries > stdout if True
    logger_module.setup_logger_handler(log_name=log_fname, log_dir=str(tmpdir))
    logger = logging.getLogger(__name__)

    # emitting some log entries
    logger.info("Test info")
    logger.debug("Test debug")

    # Test if logs were emmited to the file
    with open(str(tmpdir.join(log_fname))) as log_f:
        assert "Test info" in log_f.readline().rstrip()
        assert "Test debug" in log_f.readline().rstrip()

    # Test if logs were emmited to the stdout
    stdouterr_out, stdouterr_err = read_std()
    assert "Test info" in stdouterr_out
    assert "Test debug" in stdouterr_out


def test_tools_opts_debug(tmpdir, read_std, is_py2):
    log_fname = "convert2rhel.log"
    logger_module.setup_logger_handler(log_name=log_fname, log_dir=str(tmpdir))
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
    logger_module.setup_logger_handler(log_name=log_fname, log_dir=str(tmpdir))
    logger = logging.getLogger(__name__)
    logger.task("Some task")
    logger.file("Some task write to file")
    with pytest.raises(SystemExit):
        logger.critical("Critical error")


@pytest.mark.parametrize(
    ("log_name", "path_exists"),
    (
        ("convert2rhel.log", True),
        ("convert2rhel.log", False),
    ),
)
def test_archive_old_logger_files(log_name, path_exists, tmpdir, caplog):
    tmpdir = str(tmpdir)
    archive_dir = os.path.join(tmpdir, "archive")
    log_file = os.path.join(tmpdir, log_name)
    test_data = "test data\n"

    if path_exists:
        open(log_file, "w").write(test_data)

    logger_module.archive_old_logger_files(log_name, tmpdir)

    if path_exists:
        assert "archive" in os.listdir(tmpdir)
        archive_files = os.listdir(archive_dir)
        assert len(archive_files) == 1
        with open(os.path.join(archive_dir, archive_files[0])) as archive_f:
            assert archive_f.read() == test_data
