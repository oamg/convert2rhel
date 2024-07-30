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

from convert2rhel import actions, redhatrelease


logger = logging.getLogger(__name__)


class PkgManagerConfig(actions.Action):
    id = "PKG_MANAGER_CONFIG"

    def run(self):
        """
        Check if the distoverpkg tag inside the package manager config has been modified before the conversion and if so
        comment it out and write to the file.
        """
        super(PkgManagerConfig, self).run()

        logger.task("Convert: Patch package manager configuration file")
        pmc = redhatrelease.PkgManagerConf()
        pmc.patch()
