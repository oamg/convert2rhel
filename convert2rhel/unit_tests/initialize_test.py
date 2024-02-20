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
