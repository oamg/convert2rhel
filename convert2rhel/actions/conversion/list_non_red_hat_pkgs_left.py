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

from convert2rhel import actions, pkghandler
from convert2rhel.pkghandler import get_installed_pkgs_w_different_fingerprint, print_pkg_info
from convert2rhel.systeminfo import system_info


loggerinst = logging.getLogger(__name__)


class ListNonRedHatPkgsLeft(actions.Action):
    id = "LIST_NON_RED_HAT_PKGS_LEFT"
    dependencies = ()  # XXX

    def run(self):
        """List all the packages that have not been replaced by the
        Red Hat-signed ones during the conversion.
        """
        super(ListNonRedHatPkgsLeft, self).run()
        loggerinst.info("Listing packages not signed by Red Hat")
        non_red_hat_pkgs = get_installed_pkgs_w_different_fingerprint(system_info.fingerprints_rhel)
        if non_red_hat_pkgs:
            loggerinst.info("The following packages were left unchanged.\n")
            print_pkg_info(non_red_hat_pkgs)
        else:
            loggerinst.info("All packages are now signed by Red Hat.")
