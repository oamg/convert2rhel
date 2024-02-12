# -*- coding: utf-8 -*-
#
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

"""
Integrates host-metering with RHEL.
https://github.com/RedHatInsights/host-metering/
"""

__metaclass__ = type

import logging
import os

from convert2rhel import systeminfo
from convert2rhel.pkghandler import call_yum_cmd
from convert2rhel.subscription import get_rhsm_facts
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)


def is_running_on_hyperscaler(rhsm_facts):
    """
    Check if the system is running on hyperscaler. Currently supported
    hyperscalers are aws, azure and gcp.

    :param rhsm_facts: Facts about the system from RHSM.
    :type rhsm_facts: dict
    :return: True if the system is running on hyperscaler, False otherwise.
    :rtype: bool
    """
    is_aws = rhsm_facts.get("aws_instance_id")
    is_azure = rhsm_facts.get("azure_instance_id")
    is_gcp = rhsm_facts.get("gcp_instance_id")
    return any([is_aws, is_azure, is_gcp])


def configure_host_metering():
    """
    Decide whether to install, enable and start host-metering on the system based on the
    CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable.

    Behavior can be controlled CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable:
    - "auto": host-metering will be configured based on the above conditions
    - empty: host-metering will not be configured
    - "force": forces configuration of host-metering (e.g., even if not running on a hyperscaler)
    - any other value: behaves as empty

    :return: True if host-metering is configured successfully, False otherwise.
    :rtype: bool
    """
    env_var = os.environ.get("CONVERT2RHEL_CONFIGURE_HOST_METERING", "empty")
    if "CONVERT2RHEL_CONFIGURE_HOST_METERING" not in os.environ:
        return False

    if system_info.version.major != 7 and env_var != "force":
        logger.info("Skipping host metering configuration. Only supported for RHEL 7.")
        return False

    if env_var == "force":
        should_configure_metering = True
        logger.warning(
            "The `force' option has been used for the CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable."
            " Please note that this option is mainly used for testing and will configure host-metering unconditionally. "
            " For generic usage please use the 'auto' option."
        )
    elif env_var == "auto":
        should_configure_metering = True
    else:
        should_configure_metering = False

    rhsm_facts = get_rhsm_facts()
    is_hyperscaler = is_running_on_hyperscaler(rhsm_facts)
    if (not is_hyperscaler or not should_configure_metering) and env_var != "force":
        logger.info("Skipping host-metering configuration.")
        return False

    logger.info("Installing host-metering packages.")
    output, ret_install = call_yum_cmd("install", ["host-metering"])
    logger.debug("Output of yum call: %s" % output)
    if ret_install:
        logger.warning("Failed to install host-metering rpms.")
        return False

    if not _enable_host_metering_service():
        return False

    return systeminfo.is_systemd_managed_service_running("host-metering.service")


def _enable_host_metering_service():
    """
    Enables and starts the host metering service.

    :return: True if host-metering is enabled and started successfully, False otherwise.
    :rtype: bool
    """

    logger.info("Enabling host-metering service.")
    output, ret_enable = run_subprocess(["systemctl", "enable", "host-metering.service"])
    if output:
        logger.debug("Output of systemctl call: %s" % output)
    if ret_enable:
        logger.warning("Failed to enable host-metering service.")
        return False

    logger.info("Starting host-metering service.")
    output, ret_start = run_subprocess(["systemctl", "start", "host-metering.service"])
    if output:
        logger.debug("Output of systemctl call: %s" % output)
    if ret_start:
        logger.warning("Failed to start host-metering service.")
        return False

    if not systeminfo.is_systemd_managed_service_running("host-metering.service"):
        logger.critical_no_exit("host-metering service is not running.")
        return False
    return True
