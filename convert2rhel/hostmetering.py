# -*- coding: utf-8 -*-
#
# Copyright(C) 2023 Red Hat, Inc.
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

"""
Integrates host-metering with RHEL.
https://github.com/RedHatInsights/host-metering/
"""

__metaclass__ = type

import logging

from convert2rhel.pkghandler import call_yum_cmd
from convert2rhel.toolopts import tool_opts
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)


def configure_host_metering():
    """
    Install, enable and start host-metering on the system.

    Returns:
        bool: True if host-metering is configured successfully, False otherwise.
    """
    if not tool_opts.payg:
        logger.info("Skipping host-metering configuration.")
        return False

    logger.info("Installing host-metering rpms.")
    output, ret_install = call_yum_cmd("install", ["host-metering"])
    logger.debug("Output of yum call: %s" % output)
    if ret_install:
        logger.warning("Failed to install host-metering rpms.")
        return False

    logger.info("Enabling host-metering service.")
    output, ret_enable = run_subprocess(["systemctl", "enable", "host-metering.service"])
    logger.debug("Output of systemctl call: %s" % output)
    if ret_enable:
        logger.warning("Failed to enable host-metering service.")

    logger.info("Starting host-metering service.")
    output, ret_start = run_subprocess(["systemctl", "start", "host-metering.service"])
    logger.debug("Output of systemctl call: %s" % output)
    if ret_start:
        logger.warning("Failed to start host-metering service.")

    return not (ret_install or ret_enable or ret_start)
