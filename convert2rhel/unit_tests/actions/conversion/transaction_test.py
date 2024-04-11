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

from convert2rhel import exceptions, pkgmanager, unit_tests
from convert2rhel.actions import STATUS_CODE
from convert2rhel.actions.conversion import transaction
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.unit_tests.conftest import all_systems


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def convert_system_packages():
    return transaction.ConvertSystemPackages()


@all_systems
def test_convert_system_packages(pretend_os, convert_system_packages, monkeypatch):
    transaction_handler_instance = mock.create_autospec(TransactionHandlerBase)
    monkeypatch.setattr(
        pkgmanager,
        "create_transaction_handler",
        mock.Mock(spec=pkgmanager.create_transaction_handler, return_value=transaction_handler_instance),
    )

    convert_system_packages.run()

    assert transaction_handler_instance.run_transaction.call_count == 1
    assert transaction_handler_instance.run_transaction.call_args == mock.call()
    assert convert_system_packages.result.level == STATUS_CODE["SUCCESS"]


@all_systems
def test_convert_system_packages_unknown_error(pretend_os, convert_system_packages, monkeypatch):
    # TODO(r0x0d): Update this test once we have better execeptions to change
    # the SystemExit references.

    monkeypatch.setattr(
        pkgmanager,
        "create_transaction_handler",
        mock.Mock(
            spec=pkgmanager.create_transaction_handler,
            side_effect=exceptions.CriticalError(id_="ID", title="Title", description="Description"),
        ),
    )

    convert_system_packages.run()

    unit_tests.assert_actions_result(
        convert_system_packages,
        level="ERROR",
        id="ID",
        title="Title",
        description="Description",
    )
