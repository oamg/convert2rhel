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
import os

from convert2rhel import actions
from convert2rhel.utils import run_subprocess
from convert2rhel.utils.environment import check_environment_variable_value


logger = logging.getLogger(__name__)

LINK_KMODS_RH_POLICY = "https://access.redhat.com/third-party-software-support"
LINK_PREVENT_KMODS_FROM_LOADING = "https://access.redhat.com/solutions/41278"
LINK_TAINTED_KMOD_DOCS = "https://docs.kernel.org/admin-guide/tainted-kernels.html"


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
        diagnosis = (
            "Tainted kernel modules detected:\n  {0}\n"
            "Third-party components are not supported per our "
            "software support policy:\n{1}\n".format(module_names, LINK_KMODS_RH_POLICY)
        )

        if unsigned_modules:
            if not check_environment_variable_value("CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP"):
                self.set_result(
                    level="OVERRIDABLE",
                    id="TAINTED_KMODS_DETECTED",
                    title="Tainted kernel modules detected",
                    description="Please refer to the diagnosis for further information",
                    diagnosis=diagnosis,
                    remediations=(
                        "Prevent the modules from loading by following {0}"
                        " and run convert2rhel again to continue with the conversion."
                        " Although it is not recommended, you can disregard this message by setting the environment variable"
                        " 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP' to 1. Overriding this check can be dangerous"
                        " so it is recommended that you do a system backup beforehand."
                        " For information on what a tainted kernel module is, please refer to this documentation {1}".format(
                            LINK_PREVENT_KMODS_FROM_LOADING, LINK_TAINTED_KMOD_DOCS
                        )
                    ),
                )
                return

            self.add_message(
                level="WARNING",
                id="SKIP_TAINTED_KERNEL_MODULE_CHECK",
                title="Skip tainted kernel module check",
                description=(
                    "Detected 'CONVERT2RHEL_TAINTED_KERNEL_MODULE_CHECK_SKIP' environment variable, we will skip "
                    "the tainted kernel module check.\n"
                    "Beware, this could leave your system in a broken state."
                ),
            )
            self.add_message(
                level="WARNING",
                id="TAINTED_KMODS_DETECTED_MESSAGE",
                title="Tainted kernel modules detected",
                description="Please refer to the diagnosis for further information",
                diagnosis=diagnosis,
                remediations=(
                    "Prevent the modules from loading by following {0}"
                    " and run convert2rhel again to continue with the conversion."
                    " For information on what a tainted kernel module is, please refer to this documentation {1}".format(
                        LINK_PREVENT_KMODS_FROM_LOADING, LINK_TAINTED_KMOD_DOCS
                    )
                ),
            )
            return
        logger.info("No tainted kernel module is loaded.")
