# Copyright(C) 2024 Red Hat, Inc.
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

import pytest
import six


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import pkghandler, unit_tests
from convert2rhel.actions.conversion import list_non_red_hat_pkgs_left


@pytest.fixture
def list_non_red_hat_pkgs_left_instance():
    return list_non_red_hat_pkgs_left.ListNonRedHatPkgsLeft()


def test_list_non_red_hat_pkgs_left(list_non_red_hat_pkgs_left_instance, monkeypatch):
    list_non_red_hat_pkgs_left_mock = mock.Mock()
    monkeypatch.setattr(pkghandler, "list_non_red_hat_pkgs_left", list_non_red_hat_pkgs_left_mock)
    list_non_red_hat_pkgs_left_instance.run()
    assert list_non_red_hat_pkgs_left_mock.call_count == 1
