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

from convert2rhel import actions, exceptions, pkgmanager


logger = logging.getLogger(__name__)


class ValidatePackageManagerTransaction(actions.Action):
    id = "VALIDATE_PACKAGE_MANAGER_TRANSACTION"
    dependencies = (
        "INSTALL_RED_HAT_GPG_KEY",
        "REMOVE_EXCLUDED_PACKAGES",
        # This package can cause problems during the validation. Since no one
        # is depending on this action, it may run whenever it wants to, which
        # can cause problems.
        "REMOVE_IWLAX2XX_FIRMWARE",
        "CHECK_FIREWALLD_AVAILABILITY",
        "ENSURE_KERNEL_MODULES_COMPATIBILITY",
        "SUBSCRIBE_SYSTEM",
        "BACKUP_PACKAGE_FILES",
    )

    def run(self):
        """Validate the package manager transaction is passing the tests."""
        super(ValidatePackageManagerTransaction, self).run()

        try:
            logger.task("Prepare: Validate the %s transaction", pkgmanager.TYPE)
            transaction_handler = pkgmanager.create_transaction_handler()
            transaction_handler.run_transaction(
                validate_transaction=True,
            )
        except exceptions.CriticalError as e:
            self.set_result(
                level="ERROR",
                id=e.id,
                title=e.title,
                description=e.description,
                diagnosis=e.diagnosis,
                remediation=e.remediation,
                variables=e.variables,
            )
