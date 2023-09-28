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
from convert2rhel.pkgmanager.handlers.base import TransactionHandlerBase
from convert2rhel.unit_tests.conftest import all_systems


six.add_move(six.MovedModule("mock", "mock", "unittest.mock"))
from six.moves import mock


@pytest.fixture
def validate_package_manager_transaction():
    return transaction.ValidatePackageManagerTransaction()


def test_validate_package_manager_transaction_dependency_order(validate_package_manager_transaction):
    expected_dependencies = (
        "INSTALL_RED_HAT_GPG_KEY",
        "REMOVE_EXCLUDED_PACKAGES",
        "REMOVE_IWLAX2XX_FIRMWARE",
        "ENSURE_KERNEL_MODULES_COMPATIBILITY",
        "SUBSCRIBE_SYSTEM",
    )

    assert expected_dependencies == validate_package_manager_transaction.dependencies


@all_systems
def test_validate_package_manager_transaction(pretend_os, validate_package_manager_transaction, monkeypatch):
    transaction_handler_instance = mock.create_autospec(TransactionHandlerBase)
    monkeypatch.setattr(
        pkgmanager,
        "create_transaction_handler",
        mock.Mock(spec=pkgmanager.create_transaction_handler, return_value=transaction_handler_instance),
    )

    validate_package_manager_transaction.run()

    assert transaction_handler_instance.run_transaction.call_count == 1
    assert transaction_handler_instance.run_transaction.call_args == mock.call(validate_transaction=True)
    assert validate_package_manager_transaction.result.level == STATUS_CODE["SUCCESS"]


@all_systems
def test_validate_package_manager_transaction_unknown_error(
    pretend_os, validate_package_manager_transaction, monkeypatch
):
    # TODO(r0x0d): Update this test once we have better execeptions to change
    # the SystemExit references.

    monkeypatch.setattr(
        pkgmanager,
        "create_transaction_handler",
        mock.Mock(spec=pkgmanager.create_transaction_handler, side_effect=SystemExit("Exiting...")),
    )

    validate_package_manager_transaction.run()

    unit_tests.assert_actions_result(
        validate_package_manager_transaction,
        level="ERROR",
        id="UNKNOWN_ERROR",
        title="Unknown",
        description="The cause of this error is unknown, please look at the diagnosis for more information.",
        diagnosis="Exiting...",
    )
