# Copyright(C) 2016 Red Hat, Inc.
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

from convert2rhel import actions
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)

LINK_KMODS_RH_POLICY = "https://access.redhat.com/third-party-software-support"
LINK_PREVENT_KMODS_FROM_LOADING = "https://access.redhat.com/solutions/41278"


class TaintedKmods(actions.Action):
    id = "TAINTED_KMODS"

    def run(self):
        """Stop the conversion when a loaded tainted kernel module is detected.
         Tainted kmods ends with (...) in /proc/modules, for example:
        multipath 20480 0 - Live 0x0000000000000000
        linear 20480 0 - Live 0x0000000000000000
        system76_io 16384 0 - Live 0x0000000000000000 (OE)  <<<<<< Tainted
        system76_acpi 16384 0 - Live 0x0000000000000000 (OE) <<<<<< Tainted
        """
        super(TaintedKmods, self).run()

        logger.task("Prepare: Check if loaded kernel modules are not tainted")
        unsigned_modules, _ = run_subprocess(["grep", "(", "/proc/modules"])
        module_names = "\n  ".join([mod.split(" ")[0] for mod in unsigned_modules.splitlines()])
        if unsigned_modules:
            self.set_result(
                level="ERROR",
                id="TAINTED_KMODS_DETECTED",
                message=(
                    "Tainted kernel modules detected:\n  {0}\n"
                    "Third-party components are not supported per our "
                    "software support policy:\n {1}\n"
                    "Prevent the modules from loading by following {2}"
                    " and run convert2rhel again to continue with the conversion.".format(
                        module_names, LINK_KMODS_RH_POLICY, LINK_PREVENT_KMODS_FROM_LOADING
                    )
                ),
            )
            return
        logger.info("No tainted kernel module is loaded.")
