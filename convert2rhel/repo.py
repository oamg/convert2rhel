# -*- coding: utf-8 -*-
#
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

from convert2rhel.systeminfo import system_info


DEFAULT_YUM_REPOFILE_DIR = "/etc/yum.repos.d"
DEFAULT_YUM_VARS_DIR = "/etc/yum/vars"
DEFAULT_DNF_VARS_DIR = "/etc/dnf/vars"

loggerinst = logging.getLogger(__name__)


def get_rhel_repoids():
    """Get IDs of the Red Hat CDN repositories that correspond to the current system.

    In case the to-be-converted-OS minor version corresponds to RHEL Extended Update Support (EUS) release,
    we preferably enable the RHEL EUS repoids as those provide security updates over two years, in comparison to 6 months
    in case of the standard non-EUS repoids.
    """
    repos_needed = system_info.eus_rhsm_repoids if system_info.eus_system else system_info.default_rhsm_repoids

    loggerinst.info("RHEL repository IDs to enable: %s" % ", ".join(repos_needed))

    return repos_needed
