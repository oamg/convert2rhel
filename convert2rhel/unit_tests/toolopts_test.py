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
__metaclass__ = type

import pytest

from convert2rhel import toolopts


@pytest.mark.parametrize(
    "supported_opts",
    (
        {
            "username": "correct_username",
            "password": "correct_password",
            "activation_key": "correct_key",
            "org": "correct_org",
        },
        {
            "username": "correct_username",
            "password": "correct_password",
            "activation_key": "correct_key",
            "org": "correct_org",
            "invalid_key": "invalid_key",
        },
    ),
)
def test_set_opts(supported_opts, global_tool_opts):
    toolopts.ToolOpts.set_opts(global_tool_opts, supported_opts)

    assert global_tool_opts.username == supported_opts["username"]
    assert global_tool_opts.password == supported_opts["password"]
    assert global_tool_opts.activation_key == supported_opts["activation_key"]
    assert global_tool_opts.org == supported_opts["org"]
    assert not hasattr(global_tool_opts, "invalid_key")
