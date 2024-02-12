# -*- coding: utf-8 -*-
#
# Copyright(C) 2022 Red Hat, Inc.
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

import pytest
import six

from convert2rhel import applock, initialize
from convert2rhel import logger as logger_module
from convert2rhel import main


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.mark.parametrize(
    ("exit_code"),
    (
        (0),
        (1),
    ),
)
def test_run(monkeypatch, exit_code, tmp_path):
    monkeypatch.setattr(logger_module, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(main, "main", value=lambda: exit_code)
    monkeypatch.setattr(applock, "_DEFAULT_LOCK_DIR", str(tmp_path))
    assert initialize.run() == exit_code


def test_initialize_logger(monkeypatch):
    setup_logger_handler_mock = mock.Mock()

    monkeypatch.setattr(
        logger_module,
        "setup_logger_handler",
        value=setup_logger_handler_mock,
    )

    initialize.initialize_logger()
    setup_logger_handler_mock.assert_called_once()


@pytest.mark.parametrize(("exception_type", "exception"), ((IOError, True), (OSError, True), (None, False)))
def test_initialize_file_logging(exception_type, exception, monkeypatch, caplog):
    add_file_handler_mock = mock.Mock()
    archive_old_logger_files_mock = mock.Mock()

    if exception:
        archive_old_logger_files_mock.side_effect = exception_type

    monkeypatch.setattr(
        logger_module,
        "add_file_handler",
        value=add_file_handler_mock,
    )
    monkeypatch.setattr(
        logger_module,
        "archive_old_logger_files",
        value=archive_old_logger_files_mock,
    )

    initialize.initialize_file_logging("convert2rhel.log", "/tmp")

    if exception:
        assert caplog.records[-1].levelname == "WARNING"
        assert "Unable to archive previous log:" in caplog.records[-1].message

    add_file_handler_mock.assert_called_once()
    archive_old_logger_files_mock.assert_called_once()
