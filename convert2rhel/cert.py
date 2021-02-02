# -*- coding: utf-8 -*-
#
# Copyright(C) 2020 Red Hat, Inc.
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

import logging
import os
import shutil
import sys

from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel import utils


class SystemCert(object):
    _system_cert_dir = "/etc/pki/product-default/"

    def __init__(self):
        self._cert_path = self._get_cert_path()

    @staticmethod
    def _get_cert_path():
        loggerinst = logging.getLogger(__name__)
        cert_dir = os.path.join(utils.DATA_DIR, "rhel-certs")
        if not os.access(cert_dir, os.R_OK | os.W_OK):
            loggerinst.critical("Error: Could not access %s." % cert_dir)
        pem_filename = None
        for filename in os.listdir(cert_dir):
            if filename.endswith(".pem"):
                pem_filename = filename
                break
        if not pem_filename:
            loggerinst.critical("Error: System certificate (.pem) not found in %s." % cert_dir)
        return os.path.join(cert_dir, pem_filename)

    def install(self):
        """RHEL certificate (.pem) is used by subscription-manager to
        determine the running system type/version.
        """
        loggerinst = logging.getLogger(__name__)
        loggerinst.info("Installing RHEL certificate to the system.")

        try:
            utils.mkdir_p(self._system_cert_dir)
            shutil.copy(self._cert_path, self._system_cert_dir)
        except OSError as err:
            loggerinst.critical("OSError({0}): {1}".format(err.errno, err.strerror))

        loggerinst.debug("Certificate copied to %s." % self._system_cert_dir)
