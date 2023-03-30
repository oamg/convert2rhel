# Copyright(C) 2023 Red Hat, Inc.
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

from convert2rhel import pkgmanager, unit_tests
from convert2rhel.actions import STATUS_CODE
from convert2rhel.actions.pre_ponr_changes import transaction
from convert2rhel.unit_tests.conftest import all_systems


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def validate_package_manager_transaction():
    return transaction.ValidatePackageManagerTransaction()


def test_validate_package_manager_transaction_dependency_order(validate_package_manager_transaction):
    expected_dependencies = (
        "REMOVE_EXCLUDED_PACKAGES",
        "REMOVE_IWLAX2XX_FIRMWARE",
        "ENSURE_KERNEL_MODULES_COMPATIBILITY",
        "SUBSCRIBE_SYSTEM",
    )

    assert expected_dependencies == validate_package_manager_transaction.dependencies


class TransactionHandlerMock(unit_tests.MockFunction):
    def __init__(self):
        self.called = 0
        self.validate_transaction = False

    def run_transaction(self, validate_transaction):
        self.called += 1
        self.validate_transaction = validate_transaction


@all_systems
def test_validate_package_manager_transaction(pretend_os, validate_package_manager_transaction, monkeypatch):
    transaction_handler_instance = TransactionHandlerMock()
    monkeypatch.setattr(pkgmanager, "create_transaction_handler", lambda: transaction_handler_instance)

    validate_package_manager_transaction.run()

    assert transaction_handler_instance.called == 1
    assert transaction_handler_instance.validate_transaction
    assert validate_package_manager_transaction.status == STATUS_CODE["SUCCESS"]


@all_systems
def test_validate_package_manager_transaction_unknown_error(
    pretend_os, validate_package_manager_transaction, monkeypatch
):
    # TODO(r0x0d): Update this test once we have better execeptions to change
    # the SystemExit references.

    monkeypatch.setattr(pkgmanager, "create_transaction_handler", mock.Mock(side_effect=SystemExit("Exiting...")))

    validate_package_manager_transaction.run()

    unit_tests.assert_actions_result(
        validate_package_manager_transaction, status="ERROR", error_id="UNKNOWN_ERROR", message="Exiting..."
    )
