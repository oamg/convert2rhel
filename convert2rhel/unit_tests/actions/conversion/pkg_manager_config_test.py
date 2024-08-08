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
import pytest
import six

from convert2rhel import redhatrelease
from convert2rhel.actions.conversion import pkg_manager_config


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def pkg_manager_config_instance():
    return pkg_manager_config.ConfigurePkgManager()


def test_pkg_manager_config(pkg_manager_config_instance, monkeypatch):
    redhat_release_mock = mock.Mock()
    monkeypatch.setattr(redhatrelease.PkgManagerConf, "patch", redhat_release_mock)
    pkg_manager_config_instance.run()

    assert redhat_release_mock.call_count == 1
