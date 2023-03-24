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

import logging

from convert2rhel import actions, pkgmanager
from convert2rhel.actions.handle_packages import RemoveExcludedPackages
from convert2rhel.actions.kernel_modules import EnsureKernelModulesCompatibility
from convert2rhel.actions.special_cases import RemoveIwlax2xxFirmware
from convert2rhel.actions.subscription import SubscribeSystem


logger = logging.getLogger(__name__)


class ValidatePackageManagerTransaction(actions.Action):
    id = "VALIDATE_PACKAGE_MANAGER_TRANSACTION"
    dependencies = (
        RemoveExcludedPackages,
        # This package can cause problems during the validation. Since no one
        # is depending on this action, it may run whenever it wants to, which
        # can cause problems.
        RemoveIwlax2xxFirmware,
        EnsureKernelModulesCompatibility,
        SubscribeSystem,
    )

    @actions._action_defaults_to_success
    def run(self):
        """Validate the package manager transaction is passing the tests."""
        try:
            logger.task("Prepare: Validate the %s transaction", pkgmanager.TYPE)
            transaction_handler = pkgmanager.create_transaction_handler()
            transaction_handler.run_transaction(
                validate_transaction=True,
            )
            # TODO: Handling SystemExit here as way to speedup exception
            # handling and not refactor contents of the underlying function.
            # Most of the issues raised during that function call should be
            # handled inside the function, so, it's safe for now to only catch
            # SystemExit here, and later, change it to something more suitable.
        except SystemExit as e:
            # TODO(r0x0d): Places where we raise SystemExit and need to be
            # changed to something more specific.
            #   - Yum transaction:
            #       - Removing an package in case of conflicts
            #       - In case of exceeding Mirrors for repos
            #       - In case we reach max numbers of retry for dependency
            #         solving.
            #       - In case of transaction validation failure
            #
            #   - Dnf transaction:
            #       - If we fail to populate repository metadata
            #       - If we fail to resolve dependencies in the transaction
            #       - If we fail to download the transaction packages
            #       - If we fail to validate the transaction
            self.set_result(status="ERROR", error_id="UNKNOWN_ERROR", message=str(e))
