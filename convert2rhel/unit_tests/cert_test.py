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

from convert2rhel import unit_tests
try:
    import unittest2 as unittest  # Python 2.6 support
except ImportError:
    import unittest

import os
import shutil

from convert2rhel import cert
from convert2rhel.systeminfo import system_info
from convert2rhel.toolopts import tool_opts
from convert2rhel import utils


class TestCert(unittest.TestCase):

    # Certificates for all the supported RHEL variants
    certs = {
        "x86_64": {
            "6": "69.pem",
            "7": "69.pem",
            "8": "479.pem"
        },
        "ppc64": {
            "7": "74.pem",
        }
    }

    # Directory with all the tool data
    base_data_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                  "../data/"))

    @unit_tests.mock(utils, "DATA_DIR", unit_tests.TMP_DIR)
    def test_get_cert_path(self):
        # Check there are certificates for all the supported RHEL variants
        for arch, rhel_versions in self.certs.items():
            for rhel_version, pem in rhel_versions.items():
                utils.DATA_DIR = os.path.join(
                    self.base_data_dir, rhel_version, arch)
                cert_path = cert.SystemCert._get_cert_path()
                self.assertEqual(cert_path, "{0}/rhel-certs/{1}"
                                    .format(utils.DATA_DIR, pem))

    @unit_tests.mock(cert, "loggerinst", unit_tests.GetLoggerMocked())
    @unit_tests.mock(utils, "DATA_DIR", unit_tests.TMP_DIR)
    @unit_tests.mock(system_info, "arch", "arch")
    def test_get_cert_path_missing_cert(self):
        # Create temporary directory that has no certificate
        cert_dir = os.path.join(utils.DATA_DIR, "rhel-certs",
                                system_info.arch)
        utils.mkdir_p(cert_dir)
        # Check response for the non-existing certificate in the temporary dir
        self.assertRaises(SystemExit, cert.SystemCert._get_cert_path)
        self.assertEqual(len(cert.loggerinst.critical_msgs), 1)
        # Remove the temporary directory tree
        shutil.rmtree(os.path.join(utils.DATA_DIR, "rhel-certs"))

    @unit_tests.mock(cert, "loggerinst", unit_tests.GetLoggerMocked())
    @unit_tests.mock(utils, "DATA_DIR", unit_tests.NONEXISTING_DIR)
    @unit_tests.mock(system_info, "arch", "nonexisting_arch")
    def test_get_cert_path_nonexisting_dir(self):
        self.assertRaises(SystemExit, cert.SystemCert._get_cert_path)
        self.assertEqual(len(cert.loggerinst.critical_msgs), 1)

    @unit_tests.mock(cert.SystemCert, "_system_cert_dir", unit_tests.TMP_DIR)
    @unit_tests.mock(tool_opts, "arch", "x86_64")
    @unit_tests.mock(utils, "DATA_DIR", os.path.join(base_data_dir, "6", "x86_64"))
    def test_install_cert(self):
        # By initializing the cert object we get a path to an existing
        # certificate based on the mocked parameters above
        system_cert = cert.SystemCert()

        system_cert.install()

        cert_filename = os.path.basename(system_cert._cert_path)
        installed_cert_path = os.path.join(system_cert._system_cert_dir,
                                           cert_filename)
        self.assertTrue(os.path.exists(installed_cert_path))
        shutil.rmtree(unit_tests.TMP_DIR)
