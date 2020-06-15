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

import glob
import shutil

from convert2rhel.systeminfo import system_info
from convert2rhel import utils

_REDHAT_RELEASE_CERT_DIR = "/etc/pki/product-default/"
_SUBSCRIPTION_MANAGER_CERT_DIR = "/etc/pki/product/"


def copy_cert_for_rhel_5():
    """RHEL certificate (.pem) is used by subscription-manager to determine
    the running system type/version. On RHEL 5, subscription-manager looks for
    the certificates in /etc/pki/product/ even though the redhat-release
    package installs it in /etc/pki/product-default/. This discrepancy has been
    reported in https://bugzilla.redhat.com/show_bug.cgi?id=1321012 with
    WONTFIX status.
    """
    if system_info.version == "5":
        for cert in glob.glob(_REDHAT_RELEASE_CERT_DIR + "*.pem"):
            utils.mkdir_p(_SUBSCRIPTION_MANAGER_CERT_DIR)
            shutil.copy(cert, _SUBSCRIPTION_MANAGER_CERT_DIR)
