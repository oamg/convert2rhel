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

__metaclass__ = type

import os


def check_environment_variable_value(variable):
    """Helper method to check for the environment variable value.

    It will enforce that the environment variable value is set to some value
    other than 0.

    :param variable: The variable to be checked in `py:os.environ`
    :type variable: str
    """
    value = os.environ.get(variable, None)

    if value == 0:
        return False

    return True
