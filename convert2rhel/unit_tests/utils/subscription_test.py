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

__metaclass__ = type

from collections import namedtuple

import pytest

from convert2rhel.utils import subscription


UrlParts = namedtuple("UrlParts", ("scheme", "hostname", "port"))


@pytest.mark.parametrize(
    ("url_parts", "message"),
    (
        (
            UrlParts("gopher", "localhost", None),
            "Subscription manager must be accessed over http or https.  gopher is not valid",
        ),
        (UrlParts("http", None, None), "A hostname must be specified in a subscription-manager serverurl"),
        (UrlParts("http", "", None), "A hostname must be specified in a subscription-manager serverurl"),
    ),
)
def test_validate_serverurl_parsing(url_parts, message):
    with pytest.raises(ValueError, match=message):
        subscription._validate_serverurl_parsing(url_parts)


@pytest.mark.parametrize(
    ("username", "password", "organization", "activation_key", "no_rhsm", "expected"),
    (
        ("User1", "Password1", None, None, False, True),
        (None, None, "My Org", "12345ABC", False, True),
        ("User1", "Password1", "My Org", "12345ABC", False, True),
        (None, None, None, None, True, False),
        ("User1", None, None, "12345ABC", False, False),
        (None, None, None, None, False, False),
        ("User1", "Password1", None, None, True, False),
    ),
)
def test_should_subscribe(username, password, organization, activation_key, no_rhsm, expected, global_tool_opts):
    global_tool_opts.username = username
    global_tool_opts.password = password
    global_tool_opts.org = organization
    global_tool_opts.activation_key = activation_key
    global_tool_opts.no_rhsm = no_rhsm

    assert subscription._should_subscribe(global_tool_opts) is expected
