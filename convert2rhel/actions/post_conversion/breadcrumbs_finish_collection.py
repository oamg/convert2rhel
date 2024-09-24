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

from convert2rhel import actions, breadcrumbs


logger = logging.getLogger(__name__)


class BreadcumbsFinishCollection(actions.Action):
    id = "BREADCRUMBS_FINISH_COLLECTION"
    dependencies = (
        "KERNEL_BOOT_FILES",
        "UPDATE_GRUB",
    )

    def run(self):
        super(BreadcumbsFinishCollection, self).run()

        logger.task("Update breadcrumbs")
        breadcrumbs.breadcrumbs.finish_collection(success=True)
