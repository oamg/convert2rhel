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

import pytest

from conftest import TEST_VARS


def setup_test_metering_endpoint():
    """
    Setup custom metering endpoint to avoid sending data to production

    This url is default remote_write endpoint of Prometheus server, thus if
    something else starts Prometheus in default configuration on the host then
    the data sent can be observed there.

    If no Prometheus is running on the host, then the write will fail but
    the host-metering service will be running. This is still OK from PoV of
    convert2rhel integration test.
    """
    with open("/etc/host-metering.conf", "w") as f:
        f.write(
            """\
[host-metering]
write_url=http://localhost:9090/api/v1/write
"""
        )


# TODO (danmyway) We might boil this down to just a preparation of the envar and the endpoint
# and then use whatever basic conversion method for the conversion itself
# We do not really need to care about the output of the utility
# (host-metering installed, enabled, started) when we verify the service
# is running after the conversion


@pytest.mark.test_host_metering_conversion
def test_run_conversion_with_metering(shell, convert2rhel):
    """
    Verify that convert2rhel automatically installs, enables and starts host-metering
    service on hyperscalers on RHEL 7.9.
    """
    setup_test_metering_endpoint()

    with convert2rhel(
        "-y --serverurl {} --username {} --password {} --debug".format(
            TEST_VARS["RHSM_SERVER_URL"],
            TEST_VARS["RHSM_USERNAME"],
            TEST_VARS["RHSM_PASSWORD"],
        )
    ) as c2r:
        c2r.expect("Installing host-metering packages")
        c2r.expect("Enabling host-metering service")
        c2r.expect("Starting host-metering service")
        assert c2r.expect("Conversion successful") == 0

    assert c2r.exitstatus == 0
