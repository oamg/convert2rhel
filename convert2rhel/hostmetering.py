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
import os

from convert2rhel.pkghandler import call_yum_cmd
from convert2rhel.subscription import get_rhsm_facts
from convert2rhel.systeminfo import system_info
from convert2rhel.utils import run_subprocess


logger = logging.getLogger(__name__)


def is_running_on_hyperscaller(rhsm_facts):
    """
    Check if the system is running on hyperscaller. Currently supported
    hyperscallers are aws, azure and gcp.

    Args:
        rhsm_facts (dict): Facts about the system from RHSM.

    Returns:
        bool: True if the system is running on hyperscaller, False otherwise.
    """
    is_aws = rhsm_facts.get("aws_instance_id")
    is_azure = rhsm_facts.get("azure_instance_id")
    is_gcp = rhsm_facts.get("gcp_instance_id")
    return is_aws or is_azure or is_gcp


def configure_host_metering():
    """
    Install, enable and start host-metering on the system when it is running
    on a hyperscaller and is RHEL 7.

    Behavior can be controlled CONVERT2RHEL_CONFIGURE_HOST_METERING environment variable:
    - unset: host-metering will be configured based on the above conditions
    - "no": host-metering will not be configured
    - "force": forces configuration of host-metering (e.g., even if not running on a hyperscaller)
    - any other value: behaves as unset

    Returns:
        bool: True if host-metering is configured successfully, False otherwise.
    """
    env_var = os.environ.get("CONVERT2RHEL_CONFIGURE_HOST_METERING")
    rhsm_facts = get_rhsm_facts()
    is_rhel7 = system_info.version.major == 7
    conditions_met = is_running_on_hyperscaller(rhsm_facts) and is_rhel7

    if env_var == "force":
        should_configure_metering = True
    elif env_var == "no":
        should_configure_metering = False
    else:
        should_configure_metering = conditions_met

    if not should_configure_metering:
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
