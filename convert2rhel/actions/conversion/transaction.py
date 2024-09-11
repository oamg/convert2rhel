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


from convert2rhel import actions, exceptions, pkgmanager
from convert2rhel.logger import root_logger


logger = root_logger.getChild(__name__)


class ConvertSystemPackages(actions.Action):
    id = "CONVERT_SYSTEM_PACKAGES"

    def run(self):
        """Convert the system packages using either yum/dnf."""
        super(ConvertSystemPackages, self).run()

        try:
            logger.task("Convert: Replace system packages")
            transaction_handler = pkgmanager.create_transaction_handler()
            transaction_handler.run_transaction()
        except exceptions.CriticalError as e:
            self.set_result(
                level="ERROR",
                id=e.id,
                title=e.title,
                description=e.description,
                diagnosis=e.diagnosis,
                remediations=e.remediations,
                variables=e.variables,
            )
