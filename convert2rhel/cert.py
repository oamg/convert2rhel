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

from convert2rhel import utils


loggerinst = logging.getLogger(__name__)


class SystemCert(object):
    def __init__(self):
        self._target_cert_dir = "/etc/pki/product-default/"
        self._cert_filename, self._source_cert_dir = self._get_cert()
        self._source_cert_path = self._get_source_cert_path()
        self._target_cert_path = self._get_target_cert_path()

    @staticmethod
    def _get_cert():
        """Return name of certificate and his directory."""
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
        return pem_filename, cert_dir

    def _get_source_cert_path(self):
        return os.path.join(self._source_cert_dir, self._cert_filename)

    def _get_target_cert_path(self):
        return os.path.join(self._target_cert_dir, self._cert_filename)

    def install(self):
        """RHEL certificate (.pem) is used by subscription-manager to
        determine the running system type/version.
        """
        try:
            utils.mkdir_p(self._target_cert_dir)
            shutil.copy(self._source_cert_path, self._target_cert_dir)
        except OSError as err:
            loggerinst.critical("OSError({0}): {1}".format(err.errno, err.strerror))

        loggerinst.info("Certificate %s copied to %s." % (self._cert_filename, self._target_cert_dir))

    def remove(self):
        """Remove certificate (.pem), which was copied to system's cert dir."""
        loggerinst.task("Rollback: Removing installed RHSM certificate")

        try:
            os.remove(self._target_cert_path)
            loggerinst.info("Certificate %s removed" % self._target_cert_path)
        except OSError as err:
            if err.errno == 2:
                """Resolves RHSM error when removing certs, as the system migth not have intalled any certs yet"""
                loggernist.debug("No RHSM certificates found to be removed")
            else:
                loggerinst.error("OSError({0}): {1}".format(err.errno, err.strerror))
