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

try:
    from yum import *

    # This is added here to prevent a generic try-except in the
    # `check_package_updates`() function.
    from yum.Errors import RepoError  # lgtm[py/unused-import]

    TYPE = "yum"
except ImportError:
    from dnf import *  # pylint: disable=import-error

    # This is added here to prevent a generic try-except in the
    # `check_package_updates`() function.
    from dnf.exceptions import RepoError  # lgtm[py/unused-import]

    TYPE = "dnf"
