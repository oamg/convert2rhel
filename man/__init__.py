# -*- coding: utf-8 -*-
#
# Copyright(C) 2018 Red Hat, Inc.
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

from convert2rhel import toolopts


def get_parser():
    """Return OptionParser instance used by manpage generator."""
    cli = toolopts.CLI()
    # Show the subcommands in the SYNOPSIS section, but hide in the
    # `convert2rhel convert` section.
    cli._convert_parser.usage = cli.usage(include_subcommands=False)
    parser = cli._parser

    # Description taken out of our Confluence page.
    parser.description = (
        "The Convert2RHEL utility automates converting Red Hat Enterprise Linux "
        "derivative distributions to Red Hat Enterprise Linux. "
        "The whole conversion procedure is performed on the running RHEL derivative OS "
        "installation and a restart is needed at the end of the conversion to "
        "boot into the RHEL kernel. The utility replaces the original OS packages "
        "with the RHEL ones. Available are conversions of CentOS Linux 6/7/8, "
        "Oracle Linux 6/7/8, Scientific Linux 7, Alma Linux 8, and Rocky Linux 8 "
        "to the respective major version of RHEL.".strip()
    )
    return parser
