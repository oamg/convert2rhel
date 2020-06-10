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

import os
import re
import logging

from convert2rhel import utils

_SUPPORTED_VARIANTS = None


def is_variant_supported(variant):
    return bool(variant in get_supported_variants())


def determine_rhel_variant():
    loggerinst = logging.getLogger(__name__)
    from convert2rhel.toolopts import tool_opts
    if not tool_opts.variant:
        tool_opts.variant = _user_to_choose_rhel_variant()
    loggerinst.info("Variant: %s" % tool_opts.variant)


def _user_to_choose_rhel_variant():
    """RHEL variant to be converted to. Currently supported variants are
    Server, Client, Workstation and ComputeNode. RHEL for PowerPC is
    released as Server variant only.
    """
    count = len(get_supported_variants())
    variant_num = 0
    if count > 1:
        print_supported_variants()
        variant_num = utils.let_user_choose_item(count, "RHEL variant")
    chosen_variant = get_supported_variants()[variant_num]
    return chosen_variant


def print_supported_variants():
    """Print the supported RHEL variants to the user so they can choose one.
    """
    loggerinst = logging.getLogger(__name__)
    loggerinst.info("Choose the RHEL variant to which this system will be"
                    " converted to:")
    for index, variant in enumerate(get_supported_variants()):
        index += 1
        loggerinst.info("%s) %s" % (index, variant))
    return


def get_supported_variants():
    """Set the global variable once to not load the supported variants
    from file every time.
    """
    global _SUPPORTED_VARIANTS
    if not _SUPPORTED_VARIANTS:
        _SUPPORTED_VARIANTS = _load_supported_variants_from_file()
    return _SUPPORTED_VARIANTS


def _load_supported_variants_from_file():
    """The repo_minimap contains all the available repos whose name are
    prepended by a variant.
    """
    minimap_path = os.path.join(utils.DATA_DIR, "repo-mapping", "repo_minimap")
    minimap = utils.get_file_content(minimap_path, as_list=True)
    supported_variants = []
    for line in minimap:
        variant_found = re.match("(.+?)(-.*?)?;", line).group(1)
        if variant_found not in supported_variants:
            supported_variants.append(variant_found)

    if not supported_variants:
        supported_variants.append('Server')

    return supported_variants
