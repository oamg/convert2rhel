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

from convert2rhel.actions.conversion import list_non_red_hat_pkgs_left


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock

from convert2rhel import pkghandler, unit_tests
from convert2rhel.unit_tests import FormatPkgInfoMocked, GetInstalledPkgInformationMocked


@pytest.fixture
def list_non_red_hat_pkgs_left_instance():
    return list_non_red_hat_pkgs_left.ListNonRedHatPkgsLeft()


def test_list_non_red_hat_pkgs_left(list_non_red_hat_pkgs_left_instance, monkeypatch):
    monkeypatch.setattr(pkghandler, "format_pkg_info", FormatPkgInfoMocked())
    monkeypatch.setattr(
        pkghandler, "get_installed_pkg_information", GetInstalledPkgInformationMocked(pkg_selection="fingerprints")
    )
    list_non_red_hat_pkgs_left_instance.run()

    assert len(pkghandler.format_pkg_info.call_args[0][0]) == 1
    assert pkghandler.format_pkg_info.call_args[0][0][0].nevra.name == "pkg2"
