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


import logging
import os

from convert2rhel.pkghandler import call_yum_cmd

logger = logging.getLogger(__name__)

def check_uefi():
    """Inhibit the conversion when UEFI detected."""
    logger.task("Prepare: Checking the firmware interface type")
    if os.path.exists("/sys/firmware/efi"):
        # NOTE(pstodulk): the check doesn't have to be valid for hybrid boot
        # (e.g. AWS, Azure, OSP, ..)
        logger.critical(
            "Conversion of UEFI systems is currently not supported, see"
            " https://bugzilla.redhat.com/show_bug.cgi?id=1898314"
            " for more information."
        )
    logger.debug("Converting BIOS system")


def perform_pre_checks():
    """Perform all 'registered' checks

    Every check function in this file should be performed from here.
    This is the entry-point for this module.
    """
    check_uefi()
