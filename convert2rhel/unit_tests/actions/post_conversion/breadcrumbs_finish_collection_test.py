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

from convert2rhel.actions.post_conversion import breadcrumbs_finish_collection


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def breadcrumbs_finish_collection_instance():
    return breadcrumbs_finish_collection.BreadcumbsFinishCollection()


def test_breadcrumbs_finish_collection(monkeypatch, caplog, breadcrumbs_finish_collection_instance):
    finish_collection = mock.Mock()
    monkeypatch.setattr(breadcrumbs_finish_collection.breadcrumbs.breadcrumbs, "finish_collection", finish_collection)

    breadcrumbs_finish_collection_instance.run()

    assert "Final: Update breadcrumbs" in caplog.records[-1].message
    assert finish_collection.call_count == 1
