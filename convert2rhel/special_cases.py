# -*- coding: utf-8 -*-
#
# Copyright(C) 2021 Red Hat, Inc.
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

from convert2rhel.backup import RestorableFile
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import mkdir_p, run_subprocess


OPENJDK_RPM_STATE_DIR = "/var/lib/rpm-state/"
_SHIM_X64_PKG_PROTECTION_FILE_PATH = "/etc/yum/protected.d/shim-x64.conf"

logger = logging.getLogger(__name__)
shim_x64_pkg_protection_file = RestorableFile(_SHIM_X64_PKG_PROTECTION_FILE_PATH)  # pylint: disable=C0103


def check_and_resolve():
    perform_java_openjdk_workaround()
    unprotect_shim_x64()
    remove_iwlax2xx_firmware()


def remove_iwlax2xx_firmware():
    """Resolve a yum transaction failure on OL8 related to the iwl7260-firmware and iwlax2xx-firmware.

    The iwl7260-firmware package causes a file conflict error while trying to replace it with its RHEL counterpart.
    The reason for this happening is that the iwlax2xx-firmware is an dependency package of iwl7260-firmware in OL8,
    but in the RHEL repositories, this dependency doesn't exist, all of the files that are available under the
    iwlax2xx-firmware package in OL8, are in fact, available in the iwl7260-firmware package in RHEL, thus, we are
    removing this depedency to not cause problems with the conversion anymore.

    Related: https://bugzilla.redhat.com/show_bug.cgi?id=2078916
    """
    iwl7260_firmware = system_info.is_rpm_installed(name="iwl7260-firmware")
    iwlax2xx_firmware = system_info.is_rpm_installed(name="iwlax2xx-firmware")

    logger.info("Checking if the iwl7260-firmware and iwlax2xx-firmware packages are installed.")
    if system_info.id == "oracle" and system_info.version.major == 8:
        # If we have both of the firmware installed on the system, we need to remove the later one,
        # iwlax2xx-firmware, since this causes problem in the OL8 conversion in the replace packages step.
        if iwl7260_firmware and iwlax2xx_firmware:
            logger.info(
                "Removing the iwlax2xx-firmware package. Its content is provided by the RHEL iwl7260-firmware"
                " package."
            )
            _, exit_code = run_subprocess(["rpm", "-e", "--nodeps", "iwlax2xx-firmware"])
            if exit_code != 0:
                logger.error("Unable to remove the package iwlax2xx-firmware.")
        else:
            logger.info("The iwl7260-firmware and iwlax2xx-firmware packages are not both installed. Nothing to do.")
    else:
        logger.info("Relevant to Oracle Linux 8 only. Skipping.")


def perform_java_openjdk_workaround():
    """Resolve a yum transaction failure on CentOS/OL 6 related to the java-1.7.0-openjdk package.

    The java-1.7.0-openjdk package expects that the /var/lib/rpm-state/ directory is present. Yet, it may be missing.
    This directory is supposed to be created by the copy-jdk-configs package during the system installation, but it does
    not do that: https://bugzilla.redhat.com/show_bug.cgi?id=1620053#c14.

    If the original system has an older version of copy-jdk-configs installed than the one available in RHEL repos, the
    issue does not occur because the copy-jdk-configs is updated together with the java-1.7.0-openjdk package and a
    pretrans script of the copy-jdk-configs creates the dir.

    In case there's no newer version of copy-jdk-configs available in RHEL but a newer version of java-1.7.0-openjdk is
    available, we need to create the /var/lib/rpm-state/ directory as suggested in
    https://access.redhat.com/solutions/3573891.
    """

    logger.info("Checking if java-1.7.0-openjdk is installed.")
    if system_info.is_rpm_installed(name="java-1.7.0-openjdk"):
        logger.info(
            "Package java-1.7.0-openjdk found. Applying workaround in"
            "accordance with https://access.redhat.com/solutions/3573891."
        )
        try:
            mkdir_p(OPENJDK_RPM_STATE_DIR)
        except OSError:
            logger.warning("Unable to create the %s directory." % OPENJDK_RPM_STATE_DIR)
        else:
            logger.info("openjdk workaround applied successfully.")
    else:
        logger.info("java-1.7.0-openjdk not installed.")


# TODO(r0x0d): Remove this special case as it probably is not needed anymore since we are removing the package in the
#  oracle-7 config file.
def unprotect_shim_x64():
    """Remove the shim-x64 package protection on Oracle Linux 7 as it causes yum to traceback.

    The package is protected through the /etc/yum/protected.d/shim-x64.conf
    file. It is installed with the Oracle Linux 7 shim-x64 package. The same
    package on RHEL 7 does not install this file - it's OL specific - no need to
    add it back after a successful conversion to RHEL.

    Related: https://bugzilla.redhat.com/show_bug.cgi?id=2009368
    """

    logger.info("Checking if shim-x64 package is installed.")
    shim_x64 = system_info.is_rpm_installed(name="shim-x64")

    if shim_x64:
        logger.info("Removing shim-x64 package yum protection.")
        if system_info.id == "oracle" and system_info.version.major == 7:
            shim_x64_pkg_protection_file.backup()
            try:
                os.remove(shim_x64_pkg_protection_file.filepath)
                logger.info(
                    "'%s' removed in accordance with https://bugzilla.redhat.com/show_bug.cgi?id=2009368."
                    % shim_x64_pkg_protection_file.filepath
                )
            except OSError as err:
                # For permissions reasons (unlikely as we run as root) or because it does not exist
                logger.error("Unable to remove '%s': %s" % (shim_x64_pkg_protection_file.filepath, err.strerror))
        else:
            logger.info("Relevant to Oracle Linux 7 only. Skipping.")
    else:
        logger.info("shim-x64 package is not installed. Nothing to do.")
